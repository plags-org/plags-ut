from typing import Optional

from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.plags_form_model_data import PlagsFormModelData
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import UpdateUserInfoByManagerForm
from app_front.models import CourseUser, OrganizationUser, User
from app_front.utils.auth_util import (
    RequestContext,
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
)
from app_front.utils.time_util import get_current_datetime


class UserEditFormModelData(PlagsFormModelData[User]):
    full_name: str
    student_card_number: str
    username: str


def _unlink_escape(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return "__unlinked__" + value + "__unlinked__"


class UserProfileView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        user: User,
        *,
        form: Optional[UpdateUserInfoByManagerForm] = None,
    ) -> HttpResponse:
        organization_users = OrganizationUser.objects.filter(user=user)
        course_users = CourseUser.objects.filter(user=user, course__is_active=True)

        if form is None:
            context = RequestContext.from_legacy(request, user_authority)
            form = UpdateUserInfoByManagerForm(
                user.username,
                initial=UserEditFormModelData.from_model(user).to_form_initial(context),
            )

        return render(
            request,
            "meta_pages/profile.html",
            dict(
                user_authority=user_authority,
                organization_users=organization_users,
                course_users=course_users,
                target_user=user,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_USER
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict, user: User
    ) -> HttpResponse:
        return cls._view(request, user_authority, user)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_USER
    )
    def _post(
        cls, request: HttpRequest, user_authority: UserAuthorityDict, user: User
    ) -> HttpResponse:
        if "update_profile" in request.POST:
            return cls._post_update_profile(request, user_authority, user)
        if "unlink_user" in request.POST:
            return cls._post_unlink_user(request, user_authority, user)
        if "ban_user" in request.POST:
            return cls._post_ban_user(request, user_authority, user)
        raise Http404

    @classmethod
    def _post_update_profile(
        cls, request: HttpRequest, user_authority: UserAuthorityDict, user: User
    ) -> HttpResponse:
        form = UpdateUserInfoByManagerForm(user.username, request.POST)
        if not form.is_valid():
            messages.error(request, "Failed to update information.")
            return cls._view(request, user_authority, user, form=form)

        context = RequestContext.from_legacy(request, user_authority)
        incoming_model_data = UserEditFormModelData.from_form_cleaned_data(
            context, form.cleaned_data
        )
        current_model_data = UserEditFormModelData.from_model(user)

        if diffs := current_model_data.detect_diffs(incoming_model_data):
            incoming_model_data.apply_to_model(user)
            user.save()
            user.refresh_from_db()
            messages.success(request, f"Updated: {tuple(diffs)}")
        else:
            messages.info(request, "No changes")

        return redirect("user/profile", u_name=user.username)

    @classmethod
    def _can_be_operated(
        cls,
        request: HttpRequest,
        request_user: User,
        user: User,
        *,
        operation_name: str,
    ) -> bool:
        """ユーザーへの「何らかの操作」の適用対象としうるか"""
        # 管理者は消されたら困る
        if user.is_superuser:
            messages.error(
                request, f"{user.username} (superuser) is not {operation_name}-able."
            )
            return False
        # 本人も消されると面倒
        if user == request_user:
            messages.error(
                request, f"{user.username} (yourself) is not {operation_name}-able."
            )
            return False
        # 既に無効なユーザーはそのまま
        if not user.is_active:
            messages.error(
                request, f"{user.username} (deactivated) is not {operation_name}-able."
            )
            return False
        return True

    @classmethod
    def _post_unlink_user(
        cls, request: HttpRequest, user_authority: UserAuthorityDict, user: User
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)

        if not cls._can_be_operated(
            request, request_user, user, operation_name="unlink"
        ):
            return cls._view(request, user_authority, user)

        print("Unlink user: (user, user.password) =", (user, user.password))

        # NOTE アカウントを無効化するとともに、任意のリセット手段を封印することでアカウントの回復も防ぐ
        # NOTE 加えて、 ECCS Cloud アカウントとの関連付けも削除する
        user.is_active = False
        user.activation_pin = None
        user.email_update_pin = None
        user.password_reset_pin = None
        user.email = None
        user.google_id_info_sub = None
        user.unlinked_at = get_current_datetime()
        user.unlinked_by = request_user
        user.unlinked_email = _unlink_escape(user.email)
        user.unlinked_google_id_info_sub = _unlink_escape(user.google_id_info_sub)
        user.save()
        user.refresh_from_db()

        messages.success(request, f"Successfully unlinked {user.username} .")
        return redirect("user/profile", u_name=user.username)

    @classmethod
    def _post_ban_user(
        cls, request: HttpRequest, user_authority: UserAuthorityDict, user: User
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)

        if not cls._can_be_operated(request, request_user, user, operation_name="ban"):
            return cls._view(request, user_authority, user)

        print("Ban user: (user, user.password) =", (user, user.password))

        # NOTE アカウントを無効化するとともに、任意のリセット手段を封印することでアカウントの回復も防ぐ
        user.is_active = False
        user.activation_pin = None
        user.email_update_pin = None
        user.password_reset_pin = None
        user.banned_at = get_current_datetime()
        user.banned_by = request_user
        user.save()
        user.refresh_from_db()

        messages.success(request, f"Successfully banned {user.username} .")
        return redirect("user/profile", u_name=user.username)
