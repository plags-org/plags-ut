from typing import Optional

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.forms import UpdateUserEmailForm
from app_front.models import User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys


class UpdateEmailView(AbsPlagsView):
    @classmethod
    def _view(
        cls, request: HttpRequest, form: Optional[UpdateUserEmailForm] = None
    ) -> HttpResponse:
        if form is None:
            users = [
                (u.id, f"{u.username} <{u.email}>")
                for u in User.objects.filter(is_staff=False)
            ]
            form = UpdateUserEmailForm(users)
        return render(
            request,
            "user/update_email.html",
            dict(form=form),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_USER
    )
    def _get(cls, request: HttpRequest) -> HttpResponse:
        return cls._view(request)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_USER
    )
    def _post(cls, request: HttpRequest) -> HttpResponse:
        users = [
            (u.id, f"{u.username} <{u.email}>")
            for u in User.objects.filter(is_staff=False)
        ]
        form = UpdateUserEmailForm(users, request.POST)
        if not form.is_valid():
            return cls._view(request, form=form)

        user_id = form.cleaned_data["user"]
        email = form.cleaned_data["email"]
        user = User.objects.get(id=user_id)

        if email == user.email:
            messages.warning(request, "Input email has no change.")
        else:
            user.email = email
            user.save()
            messages.info(request, "User email update successful.")

        return redirect("user/update_email")
