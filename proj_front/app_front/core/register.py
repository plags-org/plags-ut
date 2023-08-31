from typing import Optional

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http.request import HttpRequest
from django.utils.translation import gettext_lazy as _
from pydantic.main import BaseModel

from app_front.core.exceptions import InvalidUserInputError
from app_front.core.transitory_user import get_transitory_user_for_email
from app_front.models import CourseUser, OrganizationUser, TransitoryUser, User
from app_front.utils.time_util import get_current_datetime


class RegisterActivateInput(BaseModel):
    email: str
    username: str
    password: str


def register_activate(
    request: HttpRequest, activate_input: RegisterActivateInput
) -> User:
    transitory_user: Optional[TransitoryUser] = get_transitory_user_for_email(
        activate_input.email
    )
    if transitory_user is None:
        messages.error(request, _("You are not registered. Please register again."))
        raise InvalidUserInputError
    if transitory_user.expired_at < get_current_datetime():
        messages.error(
            request, _("Your activation PIN is expired. Please register again.")
        )
        raise InvalidUserInputError
    if transitory_user.activated_at is not None:
        # NOTE Userレコードが存在するかを確認したほうが良いかもしれない
        messages.error(request, _("This user is already activated."))
        raise InvalidUserInputError
    # NOTE RegisterActivateForm.clean で上のケースは網羅されているので一応二重処理になっている
    # if transitory_user.activation_pin != activate_input.activation_pin:
    #     messages.error(request, _("Incorrect (email, activation_pin) pair."))
    #     raise InvalidUserInputError

    # email の衝突確認
    email_collision_user: Optional[User] = User.objects.filter(
        email=activate_input.email
    ).first()
    if email_collision_user is not None:
        messages.error(request, _("Account already registered and activated."))
        raise InvalidUserInputError

    # username の衝突確認
    username_collision_user: Optional[User] = User.objects.filter(
        username=activate_input.username
    ).first()
    if username_collision_user is not None:
        # ユーザー名が既存ユーザーと衝突; 別のユーザー名を決め直してもらう
        messages.error(
            request,
            _("Username %(username)s already taken. Please change your username.")
            % dict(username=activate_input.username),
        )
        raise InvalidUserInputError

    with transaction.atomic():
        activated_at = get_current_datetime()

        # TransitoryUserを更新
        transitory_user.activated_at = activated_at
        transitory_user.activation_pin = ""
        transitory_user.save()

        # Userを作成
        user: User = User.objects.create(
            username=activate_input.username,
            email=activate_input.email,
            full_name=transitory_user.full_name,
            student_card_number=transitory_user.student_card_number,
            is_faculty=transitory_user.is_faculty,
            invited_by=transitory_user.invited_by,
            activated_at=activated_at,
            timezone=settings.TIME_ZONE,
        )
        user.set_password(activate_input.password)
        user.save()

        # 初期招待先が設定されていれば追加
        if transitory_user.invited_organization is not None:
            editor: User = transitory_user.invited_by or user
            # 初期招待 Course が指定されていなければ Organization に User を登録
            if transitory_user.invited_course is None:
                OrganizationUser.objects.create(
                    organization=transitory_user.invited_organization,
                    user=user,
                    added_by=editor,
                    is_active=True,
                    is_active_updated_by=editor,
                    authority=transitory_user.invited_to_authority,
                    authority_updated_by=editor,
                )
            # 初期招待 Course が指定されているので Course に User を登録
            else:
                CourseUser.objects.create(
                    course=transitory_user.invited_course,
                    user=user,
                    added_by=editor,
                    is_active=True,
                    is_active_updated_by=editor,
                    authority=transitory_user.invited_to_authority,
                    authority_updated_by=editor,
                )

    return user
