from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import UserPasswordUpdateForm
from app_front.models import User


def _get_update_allowed(request_user: User) -> bool:
    return not request_user.is_google_auth_linked()


class AccountsPasswordUpdateView(AbsPlagsView):
    @classmethod
    def _view(
        cls, request: HttpRequest, form: UserPasswordUpdateForm = None
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        if form is None:
            form = UserPasswordUpdateForm()
        return render(
            request,
            "accounts/update_password.html",
            dict(
                form=form,
                update_allowed=_get_update_allowed(request_user),
            ),
        )

    @classmethod
    @annotate_view_endpoint()
    def _get(cls, request: HttpRequest) -> HttpResponse:
        return cls._view(request)

    @classmethod
    @annotate_view_endpoint()
    def _post(cls, request: HttpRequest) -> HttpResponse:
        request_user = get_request_user_safe(request)

        if not _get_update_allowed(request_user):
            messages.success(
                request,
                "Your PLAGS UT account is already linked to ECCS Cloud account. Login with password is not allowed.",
            )
            return redirect("profile")

        form = UserPasswordUpdateForm(request.POST)
        form.set_user(request_user)
        if not form.is_valid():
            return cls._view(request, form=form)

        password = form.cleaned_data["password1"]

        request_user.set_password(password)
        request_user.save()
        request_user.refresh_from_db()

        messages.success(request, "Password update successful.")

        return redirect("profile")
