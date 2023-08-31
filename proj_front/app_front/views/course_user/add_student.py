from typing import Iterable

from django.contrib import messages
from django.http.request import HttpRequest
from django.utils.translation import gettext_lazy as _

from app_front.core.abs_view.oc_user_view import AbsCourseUserAddView
from app_front.core.oc_user import (
    AVAILABLE_STUDENT_USER_AUTHORITY_CHOICES,
    STUDENT_USER_DEFAULT_AUTHORITY_CHOICE,
    UserChoices,
    get_non_oc_student_choices,
    get_sorted_course_students,
)
from app_front.models import Course, CourseUser, User


class CourseStudentUserAddView(AbsCourseUserAddView):
    PAGE_NAME = "course_user/add_student"

    _MANIPULATE_ACTION = "Add student"
    _MANIPULATE_DESCRIPTION = "Add student to"
    _MANIPULATE_USER_LIST_HEADING = "Current users (student)"

    _USER_AUTHORITY_CHOICES = AVAILABLE_STUDENT_USER_AUTHORITY_CHOICES
    _USER_AUTHORITY_INITIAL_CHOICE = STUDENT_USER_DEFAULT_AUTHORITY_CHOICE

    @classmethod
    def _get_current_course_users(cls, course: Course) -> Iterable[CourseUser]:
        return get_sorted_course_students(course)

    @classmethod
    def _get_candidate_course_users(
        cls, course_users: Iterable[CourseUser]
    ) -> UserChoices:
        return get_non_oc_student_choices(course_users)

    @classmethod
    def _extra_user_validation(cls, request: HttpRequest, added_user_id: int) -> bool:
        try:
            added_user = User.objects.get(id=added_user_id)
        except User.DoesNotExist:
            messages.error(
                request,
                _(f"Specified user [{added_user.username}] does not exist."),
            )
            return False

        try:
            common_id_number = added_user.get_common_id_number()
            if common_id_number is None:
                raise ValueError(f"Common ID number is None ({added_user_id=})")
        except ValueError:
            messages.error(
                request,
                _(
                    f"Common ID number is required to register. Please update [{added_user.username}]'s profile."
                ),
            )
            return False

        return True
