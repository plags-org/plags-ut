import datetime
import json
from typing import Dict, Final, Optional

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import (
    ActivationPinExpirePeriodEnum,
    CreateUserForm,
    FormChoicesType,
)
from app_front.models import (
    Course,
    OperationLog,
    Organization,
    TransitoryUser,
    User,
    UserAuthorityEnum,
)
from app_front.utils.auth_util import (
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
    raise_if_lacks_user_authority,
)
from app_front.utils.email_util import send_activation_email
from app_front.utils.parameter_decoder import generate_activation_pin
from app_front.utils.time_util import get_current_datetime

_PERIOD_UNIT_TO_SECONDS: Final[Dict[str, int]] = {
    "y": 60 * 60 * 24 * 365,
    "d": 60 * 60 * 24,
    "h": 60 * 60,
    "m": 60,
    "s": 1,
}


def _parse_period_str(period_str: str) -> datetime.timedelta:
    if (period_unit := period_str[-1:]) not in _PERIOD_UNIT_TO_SECONDS:
        raise ValueError(f"Invalid period_str: {period_str!r}")
    period = int(period_str[:-1])
    return datetime.timedelta(seconds=period * _PERIOD_UNIT_TO_SECONDS[period_unit])


class UserCreateView(AbsPlagsView):
    @classmethod
    def _build_invited_course_choices(
        cls, organization: Optional[Organization]
    ) -> Optional[FormChoicesType]:
        if organization is None:
            return None
        return tuple(
            (course.name, course.title)
            for course in Course.objects.filter(
                organization=organization, is_active=True
            )
        )

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Optional[Organization],
        *,
        form: Optional[CreateUserForm] = None,
    ) -> HttpResponse:
        if form is None:
            form = CreateUserForm(
                initial=dict(no_student_card_number=True, is_faculty=True),
                invited_course_choices=cls._build_invited_course_choices(organization),
            )
        return render(
            request,
            "user/create.html",
            dict(form=form, user_authority=user_authority, organization=organization),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_INVITE_USER_TO_ORGANIZATION
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Optional[Organization],
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_INVITE_USER_TO_ORGANIZATION
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Optional[Organization],
    ) -> HttpResponse:
        if organization is None:
            raise_if_lacks_user_authority(
                request, user_authority, UserAuthorityCapabilityKeys.CAN_INVITE_USER
            )

        form = CreateUserForm(
            request.POST,
            invited_course_choices=cls._build_invited_course_choices(organization),
        )
        if not form.is_valid():
            return cls._view(request, user_authority, organization, form=form)

        full_name = form.cleaned_data["full_name"]
        email = form.cleaned_data["email"]
        activation_pin_expire_period = form.cleaned_data["activation_pin_expire_period"]

        # email 重複検知
        if User.objects.filter(email=email).first() is not None:
            messages.error(
                request, "The account with the specified email address already exists."
            )
            return cls._view(request, user_authority, organization, form=form)

        invited_course: Optional[Course] = None
        invited_to_authority: Optional[UserAuthorityEnum] = None
        if organization is not None:
            invited_to = form.cleaned_data["invited_to"]
            if invited_to != CreateUserForm.THIS_ORGANIZATION_KEY:
                invited_course = Course.objects.filter(
                    organization=organization, name=invited_to, is_active=True
                ).first()
                if invited_course is None:
                    messages.error(request, f'No course named "{invited_to}"')
                    return cls._view(request, user_authority, organization, form=form)

            invited_to_authority = UserAuthorityEnum(
                form.cleaned_data["invited_to_authority"]
            )

        request_user = get_request_user_safe(request)
        activation_pin = generate_activation_pin()

        expire_period = _parse_period_str(activation_pin_expire_period)
        expired_at = get_current_datetime() + expire_period

        # TransitoryUserを作成
        created_transitory_user = TransitoryUser.objects.create(
            email=email,
            full_name=full_name,
            student_card_number="",
            is_faculty=True,
            invited_by=request_user,
            activation_pin=activation_pin,
            # registered_at: auto_now_add
            expired_at=expired_at,
            invited_organization=organization,
            invited_course=invited_course,
            invited_to_authority=invited_to_authority and invited_to_authority.value,
        )

        protocol_domain = f"{request.scheme}://{request.get_host()}"
        send_activation_email(
            created_transitory_user,
            protocol_domain,
            expires_at=expired_at,
            expiration_period=f" (in {ActivationPinExpirePeriodEnum(activation_pin_expire_period).label})",
        )

        # 操作ログを記録
        operation_role = OperationLog.OperationRole.ADMINISTRATOR
        operation_type = OperationLog.OperationType.INVITE_USER
        if organization is not None:
            operation_role = OperationLog.OperationRole.ORGANIZATION_MANAGER
            operation_type = OperationLog.OperationType.INVITE_USER_TO_ORGANIZATION
        OperationLog.objects.create(
            organization=organization,
            course=invited_course,
            operated_by=request_user,
            operation_role=operation_role,
            operation_type=operation_type,
            operation_details=json.dumps(
                dict(transitory_user_id=created_transitory_user.id)
            ),
        )

        messages.success(
            request,
            _(
                'Successfully created transitory user. The "Activation PIN" is sent to [{email}].'
            ).format(email=email),
        )

        # - QUESTION user/create 実行後のredirect先は user/create と transitory_user/list のどちらがよいか？
        #   - IDEA 同じ画面に両方表示すればいいという気がしてきた
        if organization:
            return redirect(
                "organization_manager/user/create", o_name=organization.name
            )
        return redirect("user/create")
