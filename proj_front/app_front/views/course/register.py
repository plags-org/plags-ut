import traceback

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.models import Course, CourseUser, Organization, UserAuthorityEnum
from app_front.utils.auth_util import UserAuthorityDict


def _can_course_be_registered(request: HttpRequest, course: Course) -> bool:
    """
    学生ユーザーのコース登録が可能な状態であるかを判定する

    - コースの登録可能フラグが落ちていれば無理
    - 当該ユーザーが既に CourseUser になっていれば（banされている場合も）無理
    """
    if not course.is_registerable:
        messages.warning(request, _("Registration for this course is closed."))
        return False

    request_user = get_request_user_safe(request)
    try:
        course_user = CourseUser.objects.get(course=course, user=request_user)
        if course_user.is_active:
            messages.info(request, _("You have already registered to this course."))
        else:
            messages.warning(
                request,
                _(
                    "You have once registered but kicked out by course manager. "
                    "If you have any objections, please contact the course manager."
                ),
            )
        return False

    except CourseUser.DoesNotExist:
        pass

    return True


class CourseRegisterView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint()
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        return render(
            request,
            "course/register.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
            ),
        )

    @classmethod
    @annotate_view_endpoint()
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        if request_user.is_faculty:
            messages.warning(
                request,
                _(
                    "Faculty users are not allowed to do self-registration for courses. "
                    "Ask organization/course managers for registration.",
                ),
            )
            return redirect("profile")

        try:
            common_id_number = request_user.get_common_id_number()
            if common_id_number is None:
                raise ValueError(f"Common ID number is None ({request_user=})")
        except ValueError:
            traceback.print_exc()
            messages.warning(
                request,
                _(
                    "Common ID number is required to register. Please update your profile."
                ),
            )
            return redirect("update_email")

        if not _can_course_be_registered(request, course):
            return render(
                request,
                "course/register.html",
                dict(
                    user_authority=user_authority,
                    organization=organization,
                    course=course,
                ),
            )

        # 新規のお客様 ようこそ
        CourseUser.objects.create(
            course=course,
            user=request_user,
            added_by=request_user,
            is_active=True,
            is_active_updated_by=request_user,
            authority=UserAuthorityEnum(UserAuthorityEnum.STUDENT).value,
            authority_updated_by=request_user,
        )

        return redirect(
            "course/top",
            o_name=organization.name,
            c_name=course.name,
        )
