from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import Course, CourseAsyncJob, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class CourseAsyncJobListView(AbsPlagsView):
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
        course_job_histories = CourseAsyncJob.objects.filter(
            organization=organization, course=course
        )
        job_histories_recent_50 = course_job_histories.order_by("-executed_at")[:50]
        return render(
            request,
            "async_job/course_list.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                job_history_list=job_histories_recent_50,
            ),
        )
