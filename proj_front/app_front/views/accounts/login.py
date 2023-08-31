import traceback

from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from app_front.core.system_settings import get_system_settings


class _CustomAuthenticationForm(AuthenticationForm):
    def clean(self) -> dict:
        raise NotImplementedError


class DefaultLoginView(LoginView):
    form_class = _CustomAuthenticationForm
    template_name = "accounts/login.html"

    def _view(self, request: HttpRequest) -> HttpResponse:
        return render(request, self.template_name)

    @property
    def extra_context(self) -> dict:
        context = {}
        try:
            context["system_settings"] = get_system_settings()
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
        return context
