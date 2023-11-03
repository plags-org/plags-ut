from typing import Optional

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import UserResetPasswordFormForm
from app_front.models import User
from app_front.utils.email_util import send_password_reset_email
from app_front.utils.exception_util import (
    ExceptionHandler,
    SystemResponsibleException,
    UserResponsibleException,
)
from app_front.utils.parameter_decoder import generate_activation_pin
from app_front.utils.time_util import get_current_datetime


class UserResetPasswordFormView(AbsPlagsView):
    @classmethod
    def _view(
        cls, request: HttpRequest, *, form: Optional[UserResetPasswordFormForm] = None
    ) -> HttpResponse:
        if form is None:
            form = UserResetPasswordFormForm()
        return render(request, "accounts/reset_password_form.html", dict(form=form))

    @classmethod
    @annotate_view_endpoint(require_login=False)
    def _get(cls, request: HttpRequest) -> HttpResponse:
        return cls._view(request)

    @classmethod
    @annotate_view_endpoint(require_login=False)
    def _post(cls, request: HttpRequest) -> HttpResponse:
        form = UserResetPasswordFormForm(request.POST)
        if not form.is_valid():
            return cls._view(request, form=form)

        email = form.cleaned_data["email"]

        with ExceptionHandler("Password Reset Form", request):
            # NOTE 任意の失敗を秘匿する 攻撃者に情報を与えないため
            try:
                try:
                    user: User = User.objects.get(email=email)
                except User.DoesNotExist as exc:
                    raise UserResponsibleException("No matching user to email") from exc

                # システム管理者、教員ユーザーでなければ Google アカウントによるログインへ誘導する
                if not user.is_superuser and not user.is_faculty:
                    SLACK_NOTIFIER.warning(
                        f"Detected invalid password reset attempt to <{email}> (student)"
                    )
                    messages.error(
                        request,
                        "Password reset is now only for faculty users. "
                        'Use "Login with ECCS Cloud" button instead of password login.',
                    )
                    return cls._view(request, form=form)

                user.password_reset_pin = generate_activation_pin()
                user.password_reset_requested_at = get_current_datetime()
                user.save()

                protocol_domain = f"{request.scheme}://{request.get_host()}"
                email_result = send_password_reset_email(user, protocol_domain)
                if not email_result.success:
                    raise SystemResponsibleException("Failed to send email")

            except UserResponsibleException:
                # NOTE 失敗しても区別なく見せるために管理者に警告だけ出して握りつぶす
                SLACK_NOTIFIER.warning(
                    f"Detected invalid password reset attempt to <{email}>"
                )

            except Exception as exc:  # pylint: disable=broad-except
                raise SystemResponsibleException(exc) from exc

            messages.info(
                request,
                "If (and only if) you correctly fill this form, the mail will be sent.",
            )

        return redirect("user/reset_password/form")
