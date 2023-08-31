from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.utils.auth_util import UserAuthorityDict


class HomeView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint()
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        return render(request, "home.html", dict(user_authority=user_authority))
