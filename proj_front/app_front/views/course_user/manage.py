from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import Course, CourseUser, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class CourseUserManageView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        course_users = (
            CourseUser.objects.filter(course=course)
            .order_by("-authority", "user__username")
            .select_related(
                "user",
                "added_by",
                "is_active_updated_by",
                "authority_updated_by",
            )
        )
        return render(
            request,
            "course_user/manage.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                course_users=course_users,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_EDIT_COURSE
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization, course)
