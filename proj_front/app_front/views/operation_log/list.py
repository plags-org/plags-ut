from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import Course, OperationLog, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class CourseFacultyOperationLogListView(AbsPlagsView):
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
        course_logs = OperationLog.objects.filter(
            organization=organization, course=course
        )
        course_logs_recent_50 = course_logs.order_by("-operated_at")[:50]
        return render(
            request,
            "operation_log/course_faculty_list.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                operation_logs=course_logs_recent_50,
            ),
        )
