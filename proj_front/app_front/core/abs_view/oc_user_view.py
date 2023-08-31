import abc
from typing import ClassVar, Iterable, Optional

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.oc_user import UserAuthorityCode, UserChoices
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.forms import MetaOCAddUserForm
from app_front.models import Course, CourseUser, Organization, UserAuthorityEnum
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.models_util import DjangoChoiceFieldChoices
from app_front.utils.time_util import get_current_datetime


class AbsCourseUserAddView(AbsPlagsView):
    PAGE_NAME: ClassVar[str]

    _MANIPULATE_ACTION: ClassVar[str]
    _MANIPULATE_DESCRIPTION: ClassVar[str]
    _MANIPULATE_USER_LIST_HEADING: ClassVar[str]

    _USER_AUTHORITY_CHOICES: ClassVar[DjangoChoiceFieldChoices]
    _USER_AUTHORITY_INITIAL_CHOICE: ClassVar[UserAuthorityCode]

    @classmethod
    @abc.abstractmethod
    def _get_current_course_users(cls, course: Course) -> Iterable[CourseUser]:
        """現在のコースユーザーの一覧を返す"""
        raise NotImplementedError

    @classmethod
    @abc.abstractmethod
    def _get_candidate_course_users(
        cls, course_users: Iterable[CourseUser]
    ) -> UserChoices:
        """コースへ登録可能なユーザーの一覧を返す（現在のコースユーザーは含まれない）"""
        raise NotImplementedError

    @classmethod
    def _extra_user_validation(cls, request: HttpRequest, added_user_id: int) -> bool:
        """操作対象のユーザーについて追加の検査が必要な場合に実装する"""
        del request, added_user_id
        return True

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        /,
        *,
        form: Optional[MetaOCAddUserForm] = None,
    ) -> HttpResponse:
        course_users = cls._get_current_course_users(course)
        user_choices = cls._get_candidate_course_users(course_users)
        if form is None:
            form = MetaOCAddUserForm(
                user_choices,
                user_authority_choices=cls._USER_AUTHORITY_CHOICES,
                initial=dict(
                    user_authority=UserAuthorityEnum(
                        cls._USER_AUTHORITY_INITIAL_CHOICE
                    ).value
                ),
            )
        return render(
            request,
            "meta_oc/manipulate_user.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                meta_oc_manipulate_action=cls._MANIPULATE_ACTION,
                meta_oc_manipulate_description=cls._MANIPULATE_DESCRIPTION,
                meta_oc_current_users_heading=cls._MANIPULATE_USER_LIST_HEADING,
                meta_oc_type="course",
                meta_oc=course,
                meta_oc_users=course_users,
                form=form,
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

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_EDIT_COURSE
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        course_users = cls._get_current_course_users(course)
        user_choices = cls._get_candidate_course_users(course_users)
        form = MetaOCAddUserForm(
            user_choices,
            request.POST,
            user_authority_choices=cls._USER_AUTHORITY_CHOICES,
        )
        if not form.is_valid():
            return cls._view(request, user_authority, organization, course, form=form)

        added_user_id = form.cleaned_data["user"]
        added_user_authority = form.cleaned_data["user_authority"]

        if not cls._extra_user_validation(request, added_user_id):
            return cls._view(request, user_authority, organization, course, form=form)

        course_user, is_created = CourseUser.objects.get_or_create(
            course=course,
            user_id=added_user_id,
            defaults=dict(
                added_by=request.user,
                is_active=True,
                is_active_updated_by=request.user,
                authority=added_user_authority,
                authority_updated_by=request.user,
            ),
        )
        if is_created:
            messages.success(
                request,
                f"User [{course_user.user.username}] successfully added. ({added_user_authority})",
            )
        elif course_user.authority != added_user_authority:
            change_detail = f"{course_user.authority} => {added_user_authority}"
            course_user.authority = added_user_authority
            course_user.authority_updated_at = get_current_datetime()
            course_user.save()
            messages.success(
                request,
                f"User [{course_user.user.username}] successfully updated. ({change_detail})",
            )
        else:
            messages.info(request, "No change detected.")

        return redirect(
            cls.PAGE_NAME,
            o_name=organization.name,
            c_name=course.name,
        )
