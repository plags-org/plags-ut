import time
import traceback
from typing import Dict, Final, Optional, Union

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from typing_extensions import TypeAlias

from app_front.config.config import APP_CONFIG
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.forms import AdministrationSendMailBulkForm
from app_front.models import CourseUser, OrganizationUser, User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.email_util import send_email_to_address, send_email_to_user

_SEND_MAIL_BULK_OBJECTIVE: Final = "SendMailBulk"

_EmailTarget: TypeAlias = str
_EmailAddress: TypeAlias = str


def _parse_targets(
    addresses_str: str,
) -> Dict[_EmailTarget, Union[User, _EmailAddress]]:
    targets: Dict[_EmailTarget, Union[User, _EmailAddress]] = {}
    for target in addresses_str.strip().split("\n"):
        user_id: Optional[int]
        try:
            user_id = int(target)
        except ValueError:
            user_id = None
        if user_id is not None:
            user = User.objects.get(id=user_id)
            targets[target] = user
        else:
            targets[target] = target
    return targets


class AdministrationSendMailBulkView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        *,
        form: Optional[AdministrationSendMailBulkForm] = None,
    ) -> HttpResponse:
        organization_users = OrganizationUser.objects.filter(user=request.user)
        course_users = CourseUser.objects.filter(user=request.user)

        if form is None:
            form = AdministrationSendMailBulkForm()

        return render(
            request,
            "administration/send_mail_bulk.html",
            dict(
                user_authority=user_authority,
                organization_users=organization_users,
                course_users=course_users,
                target_user=request.user,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.IS_SUPERUSER
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        return cls._view(request, user_authority)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.IS_SUPERUSER
    )
    def _post(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        form = AdministrationSendMailBulkForm(request.POST)
        form.set_passphrase(APP_CONFIG.ADMINISTRATION.send_mail_bulk_passphrase)

        if not form.is_valid():
            messages.warning(request, "Invalid input.")
            return cls._view(request, user_authority, form=form)

        # Parse / Validation
        targets = _parse_targets(form.cleaned_data["targets"])
        subject = form.cleaned_data["subject"]
        body_template = form.cleaned_data["body_template"]

        # Send
        errors = []
        for idx, (target_key, target) in enumerate(targets.items()):
            print(f"[{idx}/{len(targets)}]", target_key)
            time.sleep(3)
            try:
                if isinstance(target, User):
                    body_template_params = dict(email=target.email)
                    send_email_to_user(
                        _SEND_MAIL_BULK_OBJECTIVE,
                        subject,
                        body_template,
                        target,
                        body_template_params=body_template_params,
                    )
                elif isinstance(target, _EmailAddress):
                    body_template_params = dict(email=target)
                    send_email_to_address(
                        _SEND_MAIL_BULK_OBJECTIVE,
                        subject,
                        body_template,
                        target,
                        body_template_params=body_template_params,
                    )
                else:
                    raise ValueError(f"Invalid target: {target!r}")
            except Exception as exc:  # pylint: disable=broad-except
                print(f"Failed: {exc!r}")
                traceback.print_exc()
                errors.append(exc)
            else:
                print("success!")

        if errors:
            messages.warning(
                request,
                f"Send mail partially failed (fail / total: {len(errors)} / {len(targets)}).",
            )
        else:
            messages.info(request, "Send mail successful.")

        return redirect("administration/send_mail_bulk")
