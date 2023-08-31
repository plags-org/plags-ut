from typing import Optional

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import UserResetPasswordConfirmForm
from app_front.models import User
from app_front.utils.exception_util import (
    ExceptionHandler,
    SystemResponsibleException,
    UserResponsibleException,
)


class UserResetPasswordConfirmView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        *,
        form: Optional[UserResetPasswordConfirmForm] = None,
    ) -> HttpResponse:
        if form is None:
            form = UserResetPasswordConfirmForm()
        return render(request, "accounts/reset_password_confirm.html", dict(form=form))

    @classmethod
    @annotate_view_endpoint(require_login=False)
    def _get(cls, request: HttpRequest) -> HttpResponse:
        return cls._view(request)

    @classmethod
    @annotate_view_endpoint(require_login=False)
    def _post(cls, request: HttpRequest) -> HttpResponse:
        form = UserResetPasswordConfirmForm(request.POST)
        if not form.is_valid():
            return cls._view(request, form=form)

        email = form.cleaned_data["email"]
        password_reset_pin = form.cleaned_data["password_reset_pin"]
        password = form.cleaned_data["password1"]

        with ExceptionHandler("Password Reset Confirm", request):
            # NOTE 任意の失敗を秘匿する 攻撃者に情報を与えないため
            try:
                try:
                    user: User = User.objects.get(email=email)
                except User.DoesNotExist as exc:
                    raise UserResponsibleException("No matching user to email") from exc

                if password_reset_pin != user.password_reset_pin:
                    raise UserResponsibleException("Password reset PIN is incorrect")

                user.password_reset_pin = None
                user.set_password(password)
                user.save()

                login_user = authenticate(email=email, password=password)
                login(request, login_user)

                messages.success(request, _("Password reset successful."))

                return redirect("profile")

            except UserResponsibleException:
                # NOTE 失敗しても区別なく見せるために管理者に警告だけ出して握りつぶす
                SLACK_NOTIFIER.warning(
                    f"Detected invalid password reset attempt to <{email}> ({password_reset_pin=})"
                )

            except Exception as exc:  # pylint: disable=broad-except
                raise SystemResponsibleException(exc) from exc

            messages.info(
                request,
                "If (and only if) you correctly fill this form, the mail will be sent.",
            )

        return redirect("login")
