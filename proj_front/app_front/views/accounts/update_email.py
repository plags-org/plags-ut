import enum
import re
from typing import Dict, Type, Union

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.const import (
    UTOKYO_ECCS_MAIL_DOMAIN,
    UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import (
    ApplyEmailUpdateForm,
    ApplyLecturerEmailUpdateForm,
    ApplyUTokyoStudentEmailUpdateForm,
    RequestEmailUpdateForm,
    RequestLecturerEmailUpdateForm,
    RequestUTokyoStudentEmailUpdateForm,
)
from app_front.models import User
from app_front.utils.auth_util import (
    UserAuthorityDict,
    annex_user_authority,
    check_and_notify_exception,
)
from app_front.utils.email_util import send_email_update_email
from app_front.utils.parameter_decoder import generate_activation_pin
from app_front.utils.time_util import get_current_datetime


class FormClassEnum(enum.Enum):
    FACULTY = "FACULTY"
    STUDENT = "STUDENT"

    def is_faculty(self) -> bool:
        return self == self.FACULTY

    def is_student(self) -> bool:
        return self == self.STUDENT


def _get_form_class(user_authority: UserAuthorityDict) -> FormClassEnum:
    if user_authority["is_faculty"]:
        return FormClassEnum.FACULTY
    return FormClassEnum.STUDENT


_REQUEST_FORM_TABLE: Dict[FormClassEnum, Type[RequestEmailUpdateForm]] = {
    FormClassEnum.FACULTY: RequestLecturerEmailUpdateForm,
    FormClassEnum.STUDENT: RequestUTokyoStudentEmailUpdateForm,
}
_APPLY_FORM_TABLE: Dict[FormClassEnum, Type[ApplyEmailUpdateForm]] = {
    FormClassEnum.FACULTY: ApplyLecturerEmailUpdateForm,
    FormClassEnum.STUDENT: ApplyUTokyoStudentEmailUpdateForm,
}


def _get_request_form_class(
    user_authority: UserAuthorityDict,
) -> Type[RequestEmailUpdateForm]:
    return _REQUEST_FORM_TABLE[_get_form_class(user_authority)]


def _get_apply_form_class(
    user_authority: UserAuthorityDict,
) -> Type[ApplyEmailUpdateForm]:
    return _APPLY_FORM_TABLE[_get_form_class(user_authority)]


def _get_email_from_form(
    user_authority: UserAuthorityDict,
    form: Union[RequestEmailUpdateForm, ApplyEmailUpdateForm],
    /,
    *,
    field_name: str = "email",
) -> str:
    if _get_form_class(user_authority).is_faculty():
        return form.cleaned_data[field_name]
    return form.cleaned_data[field_name] + UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT


def _is_student_address(address: str) -> bool:
    eccs_address_regex = r"\d{10}" + re.escape(UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT)
    return re.fullmatch(eccs_address_regex, address, flags=re.ASCII) is not None


def _get_allow_update(request: HttpRequest, user_authority: UserAuthorityDict) -> bool:
    if _get_form_class(user_authority).is_faculty():
        return True
    request_user = get_request_user_safe(request)
    return not _is_student_address(request_user.email)


def _view(
    request: HttpRequest,
    user_authority: UserAuthorityDict,
    /,
    *,
    request_form: RequestEmailUpdateForm = None,
    apply_update_form: ApplyEmailUpdateForm = None,
) -> HttpResponse:
    if request_form is None:
        request_form = _get_request_form_class(user_authority)()

    if apply_update_form is None:
        apply_update_form = _get_apply_form_class(user_authority)()

    allow_update = _get_allow_update(request, user_authority)

    return render(
        request,
        "accounts/update_email.html",
        dict(
            form_class=_get_form_class(user_authority),
            request_form=request_form,
            apply_update_form=apply_update_form,
            allow_update=allow_update,
        ),
    )


@login_required
@check_and_notify_exception
@annex_user_authority
def _get(
    request: HttpRequest, user_authority: UserAuthorityDict, *_args, **_kwargs
) -> HttpResponse:
    return _view(request, user_authority)


@login_required
@check_and_notify_exception
@annex_user_authority
def _process_request_form(
    request: HttpRequest, user_authority: UserAuthorityDict, *_args, **_kwargs
) -> HttpResponse:
    request_user = get_request_user_safe(request)

    if not _get_allow_update(request, user_authority):
        messages.warning(
            request,
            f"Your email address is now [common ID number]@{UTOKYO_ECCS_MAIL_DOMAIN} . "
            "No other email is permitted.",
        )
        return redirect("profile")

    request_form = _get_request_form_class(user_authority)(request.POST)
    if not request_form.is_valid():
        return _view(request, user_authority, request_form=request_form)

    email = _get_email_from_form(user_authority, request_form)
    if _get_form_class(user_authority).is_faculty() and _is_student_address(email):
        messages.warning(
            request,
            f"Requested address matched to that of students: [common ID number]@{UTOKYO_ECCS_MAIL_DOMAIN} . "
            "Please specify an address that does not match this pattern.",
        )
        return _view(request, user_authority, request_form=request_form)

    with transaction.atomic():
        user: User = User.objects.get(username=request_user.username)
        if user.email_updating_to == email:
            messages.warning(request, "Requested address is already reserved for you.")
            return _view(request, user_authority)

        existing_users = User.objects.filter(email=email)
        pending_users = User.objects.filter(email_updating_to=email)
        if existing_users or pending_users:
            messages.warning(
                request,
                "Requested address is already reserved for another account. Rejected.",
            )
            return _view(request, user_authority)

        # NOTE ここで通ったからと言ってactivate側での新規登録は封じない（対予約攻撃）ので、
        #      実際にpinを見て更新する前にも確認が必要
        user.email_updating_to = email
        user.email_update_pin = generate_activation_pin()
        user.email_update_requested_at = get_current_datetime()
        user.save()

    protocol_domain = f"{request.scheme}://{request.get_host()}"
    send_email_update_email(user, protocol_domain)

    request_user.refresh_from_db()
    messages.info(request, '"Account update PIN" is sent to requested email.')
    return redirect("update_email")


@login_required
@check_and_notify_exception
@annex_user_authority
def _process_apply_update_form(
    request: HttpRequest, user_authority: UserAuthorityDict, *_args, **_kwargs
) -> HttpResponse:
    request_user = get_request_user_safe(request)

    if not _get_allow_update(request, user_authority):
        messages.warning(
            request,
            f"Your email address is now ( [common ID number]@{UTOKYO_ECCS_MAIL_DOMAIN} ). "
            "No other email is permitted.",
        )
        return redirect("profile")

    apply_update_form = _get_apply_form_class(user_authority)(request.POST)
    if not apply_update_form.is_valid():
        return _view(request, user_authority, apply_update_form=apply_update_form)

    email_updating_to = _get_email_from_form(
        user_authority, apply_update_form, field_name="email_updating_to"
    )
    email_update_pin = apply_update_form.cleaned_data["email_update_pin"]

    def _reset_update_request(user: User) -> None:
        user.email_updating_to = None
        user.email_update_pin = None
        user.email_update_requested_at = None

    with transaction.atomic():
        user: User = User.objects.get(username=request_user.username)
        if user.email_updating_to != email_updating_to:
            messages.warning(
                request, "New address is different from what was reserved."
            )
            return _view(request, user_authority)
        if user.email_update_pin != email_update_pin:
            messages.warning(request, "Account update PIN mismatch.")
            return _view(request, user_authority)

        existing_users = User.objects.filter(email=email_updating_to)
        if existing_users:
            messages.warning(
                request,
                "Reserved address is already used for another account. "
                "Please request again with another address.",
            )
            _reset_update_request(user)
            user.save()
            return _view(request, user_authority)

        user.email = email_updating_to
        _reset_update_request(user)
        user.save()

    request_user.refresh_from_db()
    messages.info(request, f"Your address is now updated to [ {email_updating_to} ] .")
    return redirect("profile")


def view_accounts_update_email(request, *args, **kwargs):
    if request.method == "POST":
        if "request" in request.POST:
            return _process_request_form(request, *args, **kwargs)
        if "apply_update" in request.POST:
            return _process_apply_update_form(request, *args, **kwargs)
    return _get(request, *args, **kwargs)
