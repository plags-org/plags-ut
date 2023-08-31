import re
import traceback

from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.forms import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from app_front.core.const import UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT
from app_front.core.system_settings import get_system_settings


class CustomAuthenticationForm(AuthenticationForm):
    def clean(self) -> dict:
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        # すでに不正な入力がなされているので検証をスキップ
        if not all((username, password)):
            return self.cleaned_data

        self.user_cache = authenticate(
            self.request, username=username, password=password
        )
        if self.user_cache is None:
            if re.fullmatch(r"\d{10}", username, flags=re.ASCII):
                username += UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT
                self.user_cache = authenticate(
                    self.request, username=username, password=password
                )

        if self.user_cache is None:
            raise self.get_invalid_login_error()

        self.confirm_login_allowed(self.user_cache)

        # Google アカウントと紐付いている場合はパスワードによる認証を拒絶する
        if self.user_cache.is_google_auth_linked():
            raise ValidationError(
                "Account is linked to ECCS Cloud Account. "
                'Use "Login with ECCS Cloud" button instead of password login.',
            )

        # システム管理者、教員ユーザーでなければ Google アカウントによるログインへ誘導する
        if not self.user_cache.is_superuser and not self.user_cache.is_faculty:
            raise ValidationError(
                "Password login is now only for faculty users. "
                'Use "Login with ECCS Cloud" button instead of password login.',
            )

        return self.cleaned_data


class LoginPasswordAuthView(LoginView):
    form_class = CustomAuthenticationForm
    template_name = "accounts/login_password_auth.html"

    def _view(self, request: HttpRequest) -> HttpResponse:
        form = CustomAuthenticationForm()
        return render(request, self.template_name, dict(form=form))

    @property
    def extra_context(self) -> dict:
        context = {}
        try:
            context["system_settings"] = get_system_settings()
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
        return context
