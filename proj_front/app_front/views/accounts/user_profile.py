import datetime
import traceback
from typing import Any, Dict, Final, Optional, Tuple, Type

from django.contrib import messages
from django.contrib.auth import login
from django.db import IntegrityError, transaction
from django.http import Http404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import (
    ConfirmCommonIdNumberForm,
    GoogleAuthTransitoryNewUserInfoForm,
    RegisterGoogleAuthUserForm,
    UpdateFacultyUserInfoForm,
    UpdateStudentUserInfoForm,
    UpdateUserInfoForm,
)
from app_front.models import CourseUser, OrganizationUser, User
from app_front.utils.auth_util import UserAuthorityDict
from app_front.utils.email_util import send_common_id_number_verification_email
from app_front.utils.parameter_decoder import (
    generate_verification_token,
    to_user_timezone,
)
from app_front.utils.time_util import get_current_datetime


class AccountsProfileView(AbsPlagsView):
    @classmethod
    def _get_appropriate_form_type(cls, is_faculty: bool) -> Type[UpdateUserInfoForm]:
        if is_faculty:
            return UpdateFacultyUserInfoForm
        return UpdateStudentUserInfoForm

    @classmethod
    def _get_appropriate_form(cls, is_faculty: bool, user: User) -> UpdateUserInfoForm:
        if is_faculty:
            return UpdateFacultyUserInfoForm(
                user.username,
                initial=dict(
                    full_name=user.full_name,
                    username=user.username,
                    flag_cooperate_on_research_anonymously=user.flag_cooperate_on_research_anonymously,
                ),
            )
        return UpdateStudentUserInfoForm(
            user.username,
            initial=dict(
                full_name=user.full_name,
                student_card_number=user.student_card_number,
                username=user.username,
                flag_cooperate_on_research_anonymously=user.flag_cooperate_on_research_anonymously,
            ),
        )

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        *,
        form: Optional[UpdateUserInfoForm] = None,
        register_google_auth_user_form: Optional[RegisterGoogleAuthUserForm] = None,
        confirm_common_id_number_form: Optional[ConfirmCommonIdNumberForm] = None,
        new_user_info_form: Optional[GoogleAuthTransitoryNewUserInfoForm] = None,
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        organization_users = OrganizationUser.objects.filter(user=request_user)
        course_users = CourseUser.objects.filter(
            user=request_user, course__is_active=True
        )

        is_faculty = user_authority["is_faculty"]

        if form is None:
            form = cls._get_appropriate_form(is_faculty, request_user)

        # 「共通 ID の関連付け」フォーム
        current_input_step: int = 0
        if request_user.is_transitory():
            current_input_step = 1
            if request_user.google_id_common_id_number_unverified is not None:
                current_input_step = 2
                if request_user.google_id_common_id_number_verification_token is None:
                    current_input_step = 3

            if register_google_auth_user_form is None and current_input_step >= 1:
                initial = dict(
                    common_id_number=request_user.google_id_common_id_number_unverified,
                )
                if request_user.google_id_common_id_number_unverified is not None:
                    initial["student_card_number"] = request_user.student_card_number
                register_google_auth_user_form = RegisterGoogleAuthUserForm(
                    initial=initial,
                )
            if confirm_common_id_number_form is None and current_input_step >= 2:
                confirm_common_id_number_form = ConfirmCommonIdNumberForm()
            if new_user_info_form is None and current_input_step >= 3:
                initial = dict(
                    full_name=request_user.full_name,
                )
                if not request_user.is_transitory_user_via_google_auth():
                    initial["student_card_number"] = request_user.student_card_number
                new_user_info_form = GoogleAuthTransitoryNewUserInfoForm(
                    initial=initial
                )
        else:
            register_google_auth_user_form = None
            confirm_common_id_number_form = None
            new_user_info_form = None

        return render(
            request,
            "meta_pages/profile.html",
            dict(
                user_authority=user_authority,
                organization_users=organization_users,
                course_users=course_users,
                target_user=request_user,
                form=form,
                current_input_step=current_input_step,
                register_google_auth_user_form=register_google_auth_user_form,
                confirm_common_id_number_form=confirm_common_id_number_form,
                new_user_info_form=new_user_info_form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        # ATTENTION 個人プロフィール画面は仮アカウントの有効化画面を兼ねている
        require_active_account=False
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        # NOTE 本人以外と管理者以外はみえちゃダメ
        # よく考えると見えない むしろ教員が学生ユーザーの情報を閲覧する方法を提供する必要がある
        return cls._view(request, user_authority)

    @classmethod
    @annotate_view_endpoint(
        # ATTENTION 個人プロフィール画面は仮アカウントの有効化画面を兼ねている
        require_active_account=False
    )
    def _post(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        # Transitoryなユーザー向けの入力処理
        if "register_google_auth_user" in request.POST:
            return cls._post_register_google_auth_user(request, user_authority)
        if "confirm_common_id_number" in request.POST:
            return cls._post_confirm_common_id_number(request, user_authority)
        if "new_user_info" in request.POST:
            return cls._post_new_user_info(request, user_authority)

        # アクティブなユーザー向けの入力処理
        if "update_profile" in request.POST:
            return cls._post_update_profile(request, user_authority)

        raise Http404

    # 共通ID確認メールの冷却時間
    _MAIL_COOL_TIME_MINUTES: Final[int] = 5

    @classmethod
    def _post_register_google_auth_user(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)

        # すでに検証を済ませているので素通し
        if not request_user.is_transitory():
            messages.success(request, "Your common ID number is already verified.")
            return redirect("profile")

        form = RegisterGoogleAuthUserForm(request.POST)
        if not form.is_valid():
            messages.warning(request, "Failed to register.")
            return cls._view(
                request, user_authority, register_google_auth_user_form=form
            )

        common_id_number = form.cleaned_data["common_id_number"]

        # NOTE 既存ユーザーであるかどうかはここでは考慮せず、ECCSアカウントの検証が完了した直後に分岐する

        with transaction.atomic():
            changes: Dict[str, Tuple[Any, Any]] = dict(
                common_id_number=(
                    request_user.google_id_common_id_number_unverified,
                    common_id_number,
                ),
            )
            changed_keys = [key for key, (new, old) in changes.items() if new != old]
            if changed_keys:
                # ATTENTION ここで email を更新してはいけない。共通IDの本人確認がまだであるため。
                #     NOTE email の更新は次の _post_confirm_common_id_number で行う。
                # request_user.email = ...
                if (
                    request_user.google_id_common_id_number_unverified
                    != common_id_number
                ):
                    # 共通IDを間違えていた場合、同じtokenでは問題が生じるため、変更と同時に再設定する
                    request_user.google_id_common_id_number_unverified = (
                        common_id_number
                    )
                    request_user.google_id_common_id_number_verification_token = (
                        generate_verification_token()
                    )

                request_user.save()
                request_user.refresh_from_db()
                messages.success(
                    request,
                    f'Information ({", ".join(changed_keys)}) update succeeded.',
                )
            else:
                messages.info(
                    request, "No difference. Information update not performed."
                )

            # 前回送信から冷却時間以上していれば確認メールを再送する
            if (
                request_user.google_id_common_id_number_verification_mail_last_sent_at
                is None
                or request_user.google_id_common_id_number_verification_mail_last_sent_at
                + datetime.timedelta(minutes=cls._MAIL_COOL_TIME_MINUTES)
                < get_current_datetime()
            ):
                protocol_domain = f"{request.scheme}://{request.get_host()}"
                email_result = send_common_id_number_verification_email(
                    request_user, protocol_domain
                )
                if not email_result.success:
                    SLACK_NOTIFIER.error(
                        "Mail send error", tracebacks=traceback.format_exc()
                    )
                    messages.error(
                        request,
                        "Common ID number verification mail is not sent. (Internal error)",
                    )
                    return redirect("profile")

                last_sent_at = get_current_datetime()
                request_user.google_id_common_id_number_verification_mail_last_sent_at = (
                    last_sent_at
                )
                request_user.save()
                request_user.refresh_from_db()
                last_sent_at_str = to_user_timezone(
                    request_user.timezone, last_sent_at
                ).strftime("%Y-%m-%d %H:%M:%S")
                messages.success(
                    request,
                    "Common ID number verification mail is sent to"
                    f" {email_result.email_history.to_address} ."
                    f" ({last_sent_at_str})",
                )
            else:
                messages.info(
                    request,
                    "Common ID number verification mail is not sent."
                    f" (Wait for {cls._MAIL_COOL_TIME_MINUTES} minutes after the previous mail)",
                )

        return redirect("profile")

    @classmethod
    def _post_confirm_common_id_number(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)

        # すでに検証を済ませているので素通し
        if not request_user.is_transitory():
            messages.success(request, "Your common ID number is already verified.")
            return redirect("profile")

        form = ConfirmCommonIdNumberForm(request.POST)
        if not form.is_valid():
            return cls._view(
                request, user_authority, confirm_common_id_number_form=form
            )

        verification_token = form.cleaned_data["verification_token"]

        # セッションユーザーの検証トークンと一致しないので不正状態
        # 主な想定: 共通IDの入力を間違え、誤送信を受けたユーザーがリンクを踏んでいるケース
        if (
            request_user.google_id_common_id_number_unverified is None
            or request_user.google_id_common_id_number_verification_token
            != verification_token
        ):
            messages.warning(request, "Incorrect verification token.")
            return cls._view(
                request, user_authority, confirm_common_id_number_form=form
            )

        # NOTE 共通IDから、既存ユーザーであるかを判定する
        common_id_number = request_user.google_id_common_id_number_unverified
        common_id_number_email = User.build_email_from_common_id_number(
            common_id_number
        )
        maybe_another_user: Optional[User] = User.objects.filter(
            email=common_id_number_email
        ).first()
        print(common_id_number_email)
        print(maybe_another_user)

        # NOTE 既存ユーザーである場合: 既存ユーザーに Google の認証情報を関連付け、仮ユーザーを無効化する
        if maybe_another_user is not None:
            existing_user: User = maybe_another_user
            with transaction.atomic():
                # 1. Google認証系の情報を、既存ユーザーへセッションユーザーから引き継ぐ
                existing_user.google_id_info_sub = request_user.google_id_info_sub
                existing_user.google_id_info_email = request_user.google_id_info_email
                existing_user.google_id_info_name = request_user.google_id_info_name
                existing_user.google_id_info_picture = (
                    request_user.google_id_info_picture
                )
                existing_user.google_auth_transitory_user = request_user

                # 2. セッションユーザーの認証系情報を除去し、無効化する
                request_user.google_id_info_sub = None
                request_user.google_id_info_email = None
                request_user.google_id_info_name = None
                request_user.google_id_info_picture = None
                request_user.is_active = False

                # 3. セッションユーザーのほうから先に保存する
                #    REASON app_front_users.google_id_info_sub の UNIQUE 制約
                request_user.save()
                existing_user.save()

            existing_user.refresh_from_db()
            request_user.refresh_from_db()

            # NOTE セッションユーザーを既存のユーザーに切り替える
            # KNOWLEDGE logout(request_user) は不要であった
            login(request, existing_user)

            messages.success(request, "Your common ID number is verified.")
            messages.info(
                request,
                "Your ECCS Cloud account is linked to your existing PLAGS UT account.",
            )
            return redirect("profile")

        # NOTE 既存ユーザーでない場合: このまま仮ユーザーを有効化する
        try:
            request_user.email = common_id_number_email
            request_user.google_id_common_id_number_verification_token = None
            request_user.save()
        except IntegrityError:
            messages.error(
                request,
                "Account already exists: specified common ID number "
                f"({request_user.google_id_common_id_number_unverified})"
                " is linked to another PLAGS UT account.",
            )
            return redirect("profile")

        request_user.refresh_from_db()
        messages.success(request, "Your common ID number is verified.")
        return redirect("profile")

    @classmethod
    def _post_new_user_info(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        is_faculty = user_authority["is_faculty"]

        # すでに検証を済ませているので素通し
        if not request_user.is_transitory():
            messages.success(request, "Your common ID number is already verified.")
            return redirect("profile")

        form = GoogleAuthTransitoryNewUserInfoForm(request.POST)
        if not form.is_valid():
            return cls._view(request, user_authority, new_user_info_form=form)

        full_name: str = form.cleaned_data["full_name"]
        student_card_number: str = form.cleaned_data["student_card_number"]

        with transaction.atomic():
            changes: Dict[str, Tuple[Any, Any]] = dict(
                full_name=(full_name, request_user.full_name),
            )
            if not is_faculty:
                changes["student_card_number"] = (
                    student_card_number,
                    request_user.student_card_number,
                )
            changed_keys = [key for key, (new, old) in changes.items() if new != old]
            if changed_keys:
                request_user.full_name = full_name
                if not is_faculty:
                    request_user.student_card_number = student_card_number
                request_user.save()

                request_user.refresh_from_db()
                messages.info(
                    request,
                    f'Information ({", ".join(changed_keys)}) update succeeded.',
                )
            else:
                messages.info(
                    request, "No difference. Information update not performed."
                )

        return redirect("profile")

    @classmethod
    def _post_update_profile(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        is_faculty = user_authority["is_faculty"]
        form = cls._get_appropriate_form_type(is_faculty)(
            request_user.username, request.POST
        )
        if not form.is_valid():
            messages.warning(request, "Failed to update information.")
            return cls._view(request, user_authority, form=form)

        full_name = form.cleaned_data["full_name"]
        # NOTE 教員用更新フォームに学生証番号の設定項目はない
        student_card_number: Optional[str] = (
            None if is_faculty else form.cleaned_data["student_card_number"]
        )
        username = form.cleaned_data["username"]
        flag_cooperate_on_research_anonymously = form.cleaned_data[
            "flag_cooperate_on_research_anonymously"
        ]

        with transaction.atomic():
            user: User = User.objects.get(username=request_user.username)
            changes: Dict[str, Tuple[Any, Any]] = dict(
                full_name=(full_name, user.full_name),
                username=(username, user.username),
                flag_cooperate_on_research_anonymously=(
                    flag_cooperate_on_research_anonymously,
                    user.flag_cooperate_on_research_anonymously,
                ),
            )
            if not is_faculty:
                changes["student_card_number"] = (
                    student_card_number,
                    user.student_card_number,
                )
            changed_keys = [key for key, (new, old) in changes.items() if new != old]
            if changed_keys:
                user.full_name = full_name
                if not is_faculty:
                    user.student_card_number = student_card_number
                user.username = username
                user.flag_cooperate_on_research_anonymously = (
                    flag_cooperate_on_research_anonymously
                )
                user.save()

                request_user.refresh_from_db()
                messages.info(
                    request,
                    f'Information ({", ".join(changed_keys)}) update succeeded.',
                )
            else:
                messages.info(
                    request, "No difference. Information update not performed."
                )

        return redirect("profile")
