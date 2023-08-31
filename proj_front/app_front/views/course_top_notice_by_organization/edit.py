import json
import traceback

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.course import get_course_choices
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import CreateCourseTopNoticeByOrganizationForm
from app_front.models import CourseTopNoticeByOrganization, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict



class CourseTopNoticeByOrganizationEditView(AbsPlagsView):
    @classmethod
    def _get_view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course_top_notice_by_organization: CourseTopNoticeByOrganization,
        *,
        form: CreateCourseTopNoticeByOrganizationForm = None,
    ) -> HttpResponse:
        course_choices = get_course_choices(organization)
        if form is None:
            form = CreateCourseTopNoticeByOrganizationForm(
                course_choices=course_choices,
                initial=dict(
                    title=course_top_notice_by_organization.title,
                    text=course_top_notice_by_organization.text,
                    is_public_to_students=course_top_notice_by_organization.is_public_to_students,
                    courses=json.loads(
                        course_top_notice_by_organization.target_course_name_list
                    ),
                ),
            )
        return render(
            request,
            "course_top_notice_by_organization/edit.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                form=form,
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
        course_top_notice_by_organization: CourseTopNoticeByOrganization,
    ) -> HttpResponse:
        return cls._get_view(
            request, user_authority, organization, course_top_notice_by_organization
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course_top_notice_by_organization: CourseTopNoticeByOrganization,
    ) -> HttpResponse:
        form = CreateCourseTopNoticeByOrganizationForm(
            request.POST, course_choices=get_course_choices(organization)
        )
        if not form.is_valid():
            return cls._get_view(
                request,
                user_authority,
                organization,
                course_top_notice_by_organization,
                form=form,
            )

        title = form.cleaned_data["title"]
        text = form.cleaned_data["text"]
        is_public_to_students = form.cleaned_data["is_public_to_students"]
        courses = form.cleaned_data["courses"]

        try:
            course_top_notice_by_organization.title = title
            course_top_notice_by_organization.text = text
            course_top_notice_by_organization.is_public_to_students = (
                is_public_to_students
            )
            course_top_notice_by_organization.target_course_name_list = json.dumps(
                courses
            )
            course_top_notice_by_organization.last_edited_by = request.user
            course_top_notice_by_organization.save()
        except Exception:
            traceback.print_exc()
            SLACK_NOTIFIER.error(
                "course_top_notice_by_organization/edit fail",
                tracebacks=traceback.format_exc(),
            )
            messages.error(
                request, "Course-top notice update failed due to unexpected an error"
            )
            return cls._get_view(
                request,
                user_authority,
                organization,
                course_top_notice_by_organization,
                form=form,
            )
        else:
            messages.success(request, "Course-top notice updated")
        return redirect(
            "course_top_notice_by_organization/list",
            o_name=organization.name,
        )
