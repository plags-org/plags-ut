import datetime
import json
from typing import Dict, List

from django.contrib import messages
from django.db.models.query import QuerySet
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from pydantic.main import BaseModel

from app_front.core.course import get_course_choices, get_courses_and_choices
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.forms import CreateCourseTopNoticeByOrganizationForm
from app_front.models import Course, CourseTopNoticeByOrganization, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict

_CourseName = str


class _CourseData(BaseModel):
    name: _CourseName
    title: str

    @staticmethod
    def from_model(record: Course) -> "_CourseData":
        return _CourseData(
            name=record.name,
            title=record.title,
        )


class _CourseTopNoticeByOrganizationData(BaseModel):
    id: int
    added_at: datetime.datetime
    added_by__username: str
    title: str
    text: str
    is_public_to_students: bool
    target_course_list: List[_CourseData]
    excluded_course_list: List[_CourseData]
    last_edited_at: datetime.datetime
    last_edited_by__username: str

    @staticmethod
    def add_select_related(
        query: QuerySet[CourseTopNoticeByOrganization],
    ) -> QuerySet[CourseTopNoticeByOrganization]:
        return query.select_related(
            "added_by",
            "last_edited_by",
        )

    @staticmethod
    def from_model(
        record: CourseTopNoticeByOrganization, courses: List[Course]
    ) -> "_CourseTopNoticeByOrganizationData":
        name_to_course: Dict[_CourseName, Course] = {
            course.name: course for course in courses
        }
        target_course_name_list = json.loads(record.target_course_name_list)
        return _CourseTopNoticeByOrganizationData(
            id=record.id,
            added_at=record.added_at,
            added_by__username=record.added_by.username,
            is_public_to_students=record.is_public_to_students,
            title=record.title,
            text=record.text,
            target_course_list=[
                _CourseData.from_model(name_to_course[name])
                for name in target_course_name_list
                if name in name_to_course
            ],
            excluded_course_list=[
                _CourseData.from_model(course)
                for name, course in name_to_course.items()
                if name not in target_course_name_list
            ],
            last_edited_at=record.last_edited_at,
            last_edited_by__username=record.last_edited_by.username,
        )


class CourseTopNoticeByOrganizationListView(AbsPlagsView):
    @classmethod
    def _get_view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        *,
        form: CreateCourseTopNoticeByOrganizationForm = None,
    ) -> HttpResponse:
        courses, course_choices = get_courses_and_choices(organization)
        query_course_top_notice_by_organization_list = (
            CourseTopNoticeByOrganization.objects.filter(
                organization=organization
            ).order_by("-last_edited_at")
        )
        course_top_notice_by_organization_list = [
            _CourseTopNoticeByOrganizationData.from_model(record, courses)
            for record in _CourseTopNoticeByOrganizationData.add_select_related(
                query_course_top_notice_by_organization_list
            )
        ]
        if form is None:
            form = CreateCourseTopNoticeByOrganizationForm(
                course_choices=course_choices
            )
        return render(
            request,
            "course_top_notice_by_organization/list.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course_top_notice_by_organization_list=course_top_notice_by_organization_list,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION,)
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        return cls._get_view(request, user_authority, organization)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        form = CreateCourseTopNoticeByOrganizationForm(
            request.POST, course_choices=get_course_choices(organization)
        )
        if not form.is_valid():
            return cls._get_view(request, user_authority, organization, form=form)

        title = form.cleaned_data["title"]
        text = form.cleaned_data["text"]
        is_public_to_students = form.cleaned_data["is_public_to_students"]
        courses = form.cleaned_data["courses"]

        CourseTopNoticeByOrganization.objects.create(
            organization=organization,
            title=title,
            text=text,
            is_public_to_students=is_public_to_students,
            target_course_name_list=json.dumps(courses),
            added_by=request.user,
            last_edited_by=request.user,
        )
        messages.success(request, "Course-top notice added")
        return redirect(
            "course_top_notice_by_organization/list",
            o_name=organization.name,
        )
