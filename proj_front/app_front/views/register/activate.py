from django.contrib.auth import authenticate, login
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.exceptions import InvalidUserInputError
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.register import RegisterActivateInput, register_activate
from app_front.forms import RegisterActivateForm


class RegisterActivateView(AbsPlagsView):
    @classmethod
    def _view(
        cls, request: HttpRequest, *, form: RegisterActivateForm = None
    ) -> HttpResponse:
        if form is None:
            form = RegisterActivateForm()
        return render(request, "register/activate.html", dict(form=form))

    @classmethod
    @annotate_view_endpoint(require_login=False)
    def _get(cls, request: HttpRequest) -> HttpResponse:
        return cls._view(request)

    @classmethod
    @annotate_view_endpoint(require_login=False)
    def _post(cls, request: HttpRequest) -> HttpResponse:
        form = RegisterActivateForm(request.POST)
        if not form.is_valid():
            return cls._view(request, form=form)

        email = form.cleaned_data["email"]
        username = form.cleaned_data["username"]
        password = form.cleaned_data["password1"]

        activate_input = RegisterActivateInput(
            email=email,
            username=username,
            password=password,
        )

        try:
            register_activate(request, activate_input)
        except InvalidUserInputError:
            return cls._view(request, form=form)

        login_user = authenticate(email=email, password=password)
        login(request, login_user)

        return redirect("profile")
