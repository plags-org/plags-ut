from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class UserListView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_MANAGE_USER,)
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        users = User.objects.all()
        return render(
            request,
            "user/list.html",
            dict(
                user_authority=user_authority,
                users=users,
            ),
        )
