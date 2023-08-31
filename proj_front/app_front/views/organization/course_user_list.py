from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.course_user import get_organization_course_users
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class OrganizationCourseUserListView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        organization_course_users = get_organization_course_users(organization)
        return render(
            request,
            "organization/course_user_list.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                organization_course_users=organization_course_users,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization)
