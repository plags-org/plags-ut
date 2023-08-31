from typing import Iterable

from app_front.core.abs_view.oc_user_view import AbsCourseUserAddView
from app_front.core.oc_user import (
    AVAILABLE_FACULTY_USER_AUTHORITY_CHOICES,
    FACULTY_USER_DEFAULT_AUTHORITY_CHOICE,
    UserChoices,
    get_non_oc_faculty_choices,
    get_sorted_course_faculties,
)
from app_front.models import Course, CourseUser


class CourseFacultyUserAddView(AbsCourseUserAddView):
    PAGE_NAME = "course_user/add_faculty"

    _MANIPULATE_ACTION = "Add faculty"
    _MANIPULATE_DESCRIPTION = "Add faculty to"
    _MANIPULATE_USER_LIST_HEADING = "Current users (faculty)"

    _USER_AUTHORITY_CHOICES = AVAILABLE_FACULTY_USER_AUTHORITY_CHOICES
    _USER_AUTHORITY_INITIAL_CHOICE = FACULTY_USER_DEFAULT_AUTHORITY_CHOICE

    @classmethod
    def _get_current_course_users(cls, course: Course) -> Iterable[CourseUser]:
        return get_sorted_course_faculties(course)

    @classmethod
    def _get_candidate_course_users(
        cls, course_users: Iterable[CourseUser]
    ) -> UserChoices:
        return get_non_oc_faculty_choices(course_users)
