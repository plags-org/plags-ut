from abc import ABCMeta
from typing import Callable, Iterable

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.oc_user import (
    AVAILABLE_FACULTY_USER_AUTHORITY_CHOICES,
    AVAILABLE_STUDENT_USER_AUTHORITY_CHOICES,
    FACULTY_USER_DEFAULT_AUTHORITY_CHOICE,
    STUDENT_USER_DEFAULT_AUTHORITY_CHOICE,
    UserAuthorityCode,
    get_oc_user_choices,
    get_sorted_course_faculties,
    get_sorted_course_students,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.forms import KEY_REMOVE, MetaOCChangeUserForm
from app_front.models import Course, CourseUser, Organization, User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.models_util import DjangoChoiceFieldChoices
from app_front.utils.time_util import get_current_datetime


class _AbsCourseUserChangeView(AbsPlagsView, metaclass=ABCMeta):
    MANIPULATE_ACTION: str
    MANIPULATE_DESCRIPTION: str

    USER_AUTHORITY_CHOICES: DjangoChoiceFieldChoices
    USER_DEFAULT_AUTHORITY: UserAuthorityCode

    REDIRECT_TARGET: str
    COURSE_USER_GETTER: Callable[[Course], Iterable[CourseUser]]

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        course_users: Iterable[CourseUser],
        form: MetaOCChangeUserForm = None,
    ) -> HttpResponse:
        if form is None:
            user_choices = get_oc_user_choices(course_users)
            form = MetaOCChangeUserForm(
                user_choices,
                user_authority_choices=cls.USER_AUTHORITY_CHOICES,
                initial=dict(user_authority=cls.USER_DEFAULT_AUTHORITY),
            )

        return render(
            request,
            "meta_oc/manipulate_user.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                meta_oc_manipulate_action=cls.MANIPULATE_ACTION,
                meta_oc_manipulate_description=cls.MANIPULATE_DESCRIPTION,
                meta_oc_type="course",
                meta_oc=course,
                meta_oc_users=course_users,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_COURSE,)
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        course_users = cls.COURSE_USER_GETTER(course)
        return cls._view(request, user_authority, organization, course, course_users)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_COURSE,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        course_users = cls.COURSE_USER_GETTER(course)

        user_choices = get_oc_user_choices(course_users)
        form = MetaOCChangeUserForm(user_choices, request.POST)

        if not form.is_valid():
            return cls._view(
                request, user_authority, organization, course, course_users, form=form
            )

        changed_user_id = form.cleaned_data["user"]
        changed_user_authority = form.cleaned_data["user_authority"]

        try:
            course_user = CourseUser.objects.get(
                course=course,
                user_id=changed_user_id,
            )
            if changed_user_authority == KEY_REMOVE:
                CourseUser.objects.filter(
                    course=course,
                    user_id=changed_user_id,
                ).delete()
                messages.success(
                    request, f"User [{course_user.user.username}] successfully removed."
                )
            elif course_user.authority != changed_user_authority:
                change_detail = f"{course_user.authority} => {changed_user_authority}"
                course_user.authority = changed_user_authority
                course_user.authority_updated_at = get_current_datetime()
                course_user.save()
                messages.success(
                    request,
                    f"User [{course_user.user.username}] successfully updated. ({change_detail})",
                )
            else:
                messages.info(request, "No change detected.")

        except CourseUser.DoesNotExist:
            user = User.objects.get(id=changed_user_id)
            messages.error(
                request, f'User "{user.username}" has already removed from course.'
            )

        return redirect(
            cls.REDIRECT_TARGET,
            o_name=organization.name,
            c_name=course.name,
        )


class CourseStudentUserChangeView(_AbsCourseUserChangeView):
    MANIPULATE_ACTION: str = "Change"
    MANIPULATE_DESCRIPTION: str = "Change authority of student user in"

    USER_AUTHORITY_CHOICES: DjangoChoiceFieldChoices = (
        AVAILABLE_STUDENT_USER_AUTHORITY_CHOICES
    )
    USER_DEFAULT_AUTHORITY: UserAuthorityCode = STUDENT_USER_DEFAULT_AUTHORITY_CHOICE

    REDIRECT_TARGET: str = "course_user/change_student"
    COURSE_USER_GETTER: Callable[
        [Course], Iterable[CourseUser]
    ] = get_sorted_course_students


class CourseFacultyUserChangeView(_AbsCourseUserChangeView):
    MANIPULATE_ACTION: str = "Change"
    MANIPULATE_DESCRIPTION: str = "Change authority of faculty user in"

    USER_AUTHORITY_CHOICES: DjangoChoiceFieldChoices = (
        AVAILABLE_FACULTY_USER_AUTHORITY_CHOICES
    )
    USER_DEFAULT_AUTHORITY: UserAuthorityCode = FACULTY_USER_DEFAULT_AUTHORITY_CHOICE

    REDIRECT_TARGET: str = "course_user/change_faculty"
    COURSE_USER_GETTER: Callable[
        [Course], Iterable[CourseUser]
    ] = get_sorted_course_faculties
