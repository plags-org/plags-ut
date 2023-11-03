import contextlib
from typing import Optional

import Levenshtein
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from pydantic import EmailStr
from pydantic import ValidationError as _PydanticValidationError
from pydantic import parse_obj_as


def _is_similar_string(a: str, b: str, min_distance_to_allow: int) -> bool:
    # NOTE 短すぎると比較的容易に含んでしまうので飛ばす 本来的には一定長以上の部分一致などを落とすべきか
    if min(len(a), len(b)) >= 4 and ((a in b) or (b in a)):
        return True
    if Levenshtein.distance(a, b) < min_distance_to_allow:
        return True
    return False


def _is_similar_to_password(
    password: str, string: str, min_distance_to_allow: int
) -> bool:
    if _is_similar_string(password, string, min_distance_to_allow):
        return True
    if _is_similar_string(password, string[::-1], min_distance_to_allow):
        return True
    return False


def validate_password(
    email: str,
    password: str,
    pin: Optional[str],
    username: str,
    student_card_number: str,
) -> None:
    """
    パスワードに関してはより強固な規則が必要
    - メールアドレスやユーザー名と近いパスワードは許さない
    - 以前のパスワードと近いパスワードは許さない（この部分では考慮しなくて良い）
    - `pin` と近いパスワードは許さない
    """
    # パスワードとして許容しうる最小距離
    min_password_email_distance_to_allow = 4
    min_password_pin_distance_to_allow = 5  # '_' を消すとかすると4になるので5
    min_password_username_distance_to_allow = 4
    min_password_student_card_number_distance_to_allow = 4

    if _is_similar_to_password(password, email, min_password_email_distance_to_allow):
        raise ValidationError(
            _("Requested password is too similar to your email address.")
        )

    email_local = email.split("@", maxsplit=1)[0]
    if _is_similar_to_password(
        password, email_local, min_password_email_distance_to_allow
    ):
        raise ValidationError(
            _("Requested password is too similar to your email address.")
        )

    if pin is not None and _is_similar_to_password(
        password, pin, min_password_pin_distance_to_allow
    ):
        raise ValidationError(_("Requested password is too similar to current PIN."))

    if _is_similar_to_password(
        password, username, min_password_username_distance_to_allow
    ):
        raise ValidationError(_("Requested password is too similar to your username."))

    if _is_similar_to_password(
        password,
        student_card_number,
        min_password_student_card_number_distance_to_allow,
    ):
        raise ValidationError(
            _("Requested password is too similar to your student card number.")
        )

    # password は email-address としての validation を通ってはいけない
    with contextlib.suppress(_PydanticValidationError):
        if parse_obj_as(EmailStr, password):
            raise ValidationError(_("Cannot use email address as password."))

    # KNOWLEDGE 共通 ID のようなものは Django により弾かれる
    # > This password is entirely numeric.
