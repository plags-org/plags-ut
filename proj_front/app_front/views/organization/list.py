from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class OrganizationListView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
    ) -> HttpResponse:
        organizations = Organization.objects.all()
        return render(
            request,
            "organization/list.html",
            dict(
                user_authority=user_authority,
                organizations=organizations,
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
