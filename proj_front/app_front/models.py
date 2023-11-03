"""
Database models
"""
import datetime
import enum
import os
import pathlib
import secrets
import traceback
from typing import Any, Optional, Tuple

from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db.models import (
    BinaryField,
    BooleanField,
    CharField,
    DateTimeField,
    EmailField,
    FileField,
    ForeignKey,
    GenericIPAddressField,
    Index,
    IntegerField,
    Model,
    TextField,
)
from django.db.models.deletion import CASCADE, PROTECT, SET_NULL
from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _
from timezone_field import TimeZoneField

from app_front.core.const import (
    DATABASE_DEVELOP_FILE_ROOT_PATH,
    DATABASE_JOB_OUTCOME_FILE_ROOT_PATH,
    DATABASE_SUBMISSION_FILE_ROOT_PATH,
    DATABASE_SUBMISSION_PARCEL_FILE_ROOT_PATH,
    UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT,
)
from app_front.core.deadlines import (
    DeadlineOrigin,
    calculate_begins_at_with_origin,
    calculate_checks_at_with_origin,
    calculate_closes_at_with_origin,
    calculate_ends_at_with_origin,
    calculate_opens_at_with_origin,
)
from app_front.core.types import Activeness
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.utils.models_util import (
    ChoosableEnum,
    ChoosableEnumField,
    ChoosableIntegerEnumField,
    CommonIDNumberValidator,
    UsernameValidator,
    str_of_int_sort_safe,
)
from app_front.utils.time_util import get_current_datetime

APP_NAME = os.path.split(pathlib.Path(os.path.abspath(__file__)).parent)[1]


class ApplicationDataVersionHistory(Model):
    # dimension
    major_version = IntegerField()
    minor_version = IntegerField()
    patch_version = IntegerField()

    class Meta:
        db_table = f"{APP_NAME}_application_data_version_histories"

        unique_together = (("major_version", "minor_version", "patch_version"),)

    # constant
    created_at = DateTimeField(auto_now_add=True)


class ActivenessEnum:
    # 01: 有効データ
    ACTIVE: Activeness = 1
    # 11: 非表示データ
    HIDDEN: Activeness = 11
    # 31: 不使用データ
    UNUSED: Activeness = 31
    # 51: 歴史的記録データ
    LEGACY: Activeness = 51
    # 71: 論理削除データ
    SHALLOW_DELETED: Activeness = 71
    # 91: 完全論理削除データ
    DEEP_DELETED: Activeness = 91


def ActivenessField(**kwargs: Any) -> IntegerField:  # type:ignore[type-arg]
    return ChoosableIntegerEnumField(ActivenessEnum, **kwargs)


class UserAuthorityEnum(ChoosableEnum):
    READONLY = "10_readonly"
    ANONYMOUS = "20_anonymous"
    STUDENT = "30_student"
    ASSISTANT = "50_assistant"
    LECTURER = "70_lecturer"
    MANAGER = "90_manager"

    def is_readonly(self) -> bool:
        return self == self.READONLY

    def is_anonymous(self) -> bool:
        return self == self.ANONYMOUS

    def is_student(self) -> bool:
        return self == self.STUDENT

    def is_assistant(self) -> bool:
        return self == self.ASSISTANT

    def is_lecturer(self) -> bool:
        return self == self.LECTURER

    def is_manager(self) -> bool:
        return self == self.MANAGER

    def __lt__(self, rhs: "UserAuthorityEnum") -> bool:
        return self.value < rhs.value

    def __le__(self, rhs: "UserAuthorityEnum") -> bool:
        return self.value <= rhs.value

    def is_as_readonly(self) -> bool:
        return self.READONLY <= self

    def is_as_anonymous(self) -> bool:
        return self.ANONYMOUS <= self

    def is_as_student(self) -> bool:
        return self.STUDENT <= self

    def is_as_assistant(self) -> bool:
        return self.ASSISTANT <= self

    def is_as_lecturer(self) -> bool:
        return self.LECTURER <= self

    def is_as_manager(self) -> bool:
        return self.MANAGER <= self

    def is_gt_readonly(self) -> bool:
        return self.READONLY < self

    def is_gt_anonymous(self) -> bool:
        return self.ANONYMOUS < self

    def is_gt_student(self) -> bool:
        return self.STUDENT < self

    def is_gt_assistant(self) -> bool:
        return self.ASSISTANT < self

    def is_gt_lecturer(self) -> bool:
        return self.LECTURER < self

    def to_display_name(self) -> str:
        return self.name.lower()


def UserAuthorityEnumField(**kwargs: Any) -> CharField:  # type:ignore[type-arg]
    return ChoosableEnumField(UserAuthorityEnum, **kwargs)


# replacement of UnicodeUsernameValidator
# user related columns
class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """
        Create and save a user with the given email, email, and password.
        """
        if not email:
            raise ValueError("email must be set")

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        if extra_fields.get("is_staff") is not False:
            raise ValueError("User must have is_staff=False.")
        if extra_fields.get("is_superuser") is not False:
            raise ValueError("User must have is_superuser=False.")
        extra_fields.setdefault("invited_by_id", 1)

        return self._create_user(email, password, **extra_fields)

    def create_staff(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", False)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Staff must have is_staff=True.")
        if extra_fields.get("is_superuser") is not False:
            raise ValueError("Staff must have is_superuser=False.")
        extra_fields.setdefault("invited_by_id", 1)

        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        extra_fields.setdefault("invited_by_id", 1)

        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser):
    """
    Users within ProgramJudgeOnline authentication system are represented by this model.

    Email and password are required. Other fields are optional.
    """

    # Eメール。ログイン時に使用
    # ATTENTION Google OAuth によるユーザー認証を行うユーザーの場合、passwordは未設定となり
    #           email だけ設定されている状態になるので、通常の Account ID / password の認証では
    #           ログインできなくなる。
    email_validator = EmailValidator()
    email = EmailField(
        _("email address"),
        null=True,
        unique=True,
        help_text=_("Valid email address."),
        validators=[email_validator],
    )

    # 授業用の表示名として、ニックネームを記入させる。公開情報である注意書きを明記する。
    username_validator = UsernameValidator()
    username = CharField(
        _("username"),
        max_length=32,
        unique=True,
        help_text=_(
            "Required. Between 4 to 32 characters. Letters, digits and _(underscores) only."
        ),
        validators=[username_validator],
    )

    # optional fields
    first_name = CharField(_("first name"), max_length=32, blank=True)
    last_name = CharField(_("last name"), max_length=128, blank=True)

    # 成績処理のために、学生証番号と氏名を記入させる。氏名表記は、ITC-LMSからのコピペを推奨する。
    full_name = CharField(_("full_name"), max_length=128, blank=True)

    # ハイフン込みで記入させてplags_frontないしクライアント側で形式（XX-XXXXXX）のvalidationを掛ける。
    # student_card_number_validator = ...  # 既に XXXXXXXX のデータが存在してしまっているので、クリーンアップするまで残す
    student_card_number = CharField(_("student card number"), max_length=32, blank=True)

    # 教員であるか
    is_faculty = BooleanField(default=False)

    joined_at = DateTimeField(_("joined at"), auto_now_add=True)

    # user that created this user
    # NOTE: null because of mutual reference, consistency must satisfied by programmer
    invited_by = ForeignKey("self", PROTECT, related_name="invited_users", null=True)

    banned_at = DateTimeField(_("banned at"), null=True)
    banned_by = ForeignKey("self", PROTECT, related_name="banned_users", null=True)

    unlinked_at = DateTimeField(_("unlinked at"), null=True)
    unlinked_by = ForeignKey("self", PROTECT, related_name="unlinked_users", null=True)
    unlinked_email = CharField(max_length=500, null=True)
    unlinked_google_id_info_sub = CharField(max_length=300, null=True)

    is_superuser = BooleanField(
        _("superuser status"),
        default=False,
        help_text=_(
            "Designates that this user has all permissions without "
            "explicitly assigning them."
        ),
    )
    is_staff = BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    ################################################################
    # user configurable options

    # initial activation
    activation_pin = CharField(max_length=64, null=True)
    activated_at = DateTimeField(_("activated at"), null=True)

    # email update pin
    email_updating_to_validator = EmailValidator()
    email_updating_to = EmailField(
        _("new email address"),
        null=True,
        unique=True,
        help_text=_("Valid email address."),
        validators=[email_updating_to_validator],
    )
    email_update_pin = CharField(max_length=64, null=True)
    email_update_requested_at = DateTimeField(_("email update requested at"), null=True)

    password_reset_pin = CharField(max_length=64, null=True)
    password_reset_requested_at = DateTimeField(
        _("password reset requested at"), null=True
    )

    # Google OAuth
    # Maximum length of 255 case-sensitive ASCII characters.
    # cf. <https://developers.google.com/identity/protocols/oauth2/openid-connect?hl=lt>
    google_id_info_sub = CharField(max_length=255, null=True, unique=True)
    google_id_info_email_validator = EmailValidator()
    google_id_info_email = EmailField(
        _("Google email address"),
        null=True,
        help_text=_("Valid google email address."),
        validators=[google_id_info_email_validator],
    )
    google_id_info_name = CharField(_("Google id name"), max_length=128, null=True)
    google_id_info_picture = CharField(
        _("Google id picture"), max_length=128, null=True
    )

    google_id_common_id_number_unverified = CharField(
        _("Common ID number (unverified)"), max_length=10, null=True
    )
    google_id_common_id_number_verification_token = CharField(
        _("Common ID number verification token"), max_length=64, null=True
    )
    google_id_common_id_number_verification_mail_last_sent_at = DateTimeField(
        _("Common ID number verification mail last sent at"), null=True
    )

    # Google ID を関連付けた際に経由した仮ユーザーのID（デバッグ時の追跡用）
    # NOTE: null because of mutual reference, consistency must satisfied by programmer
    google_auth_transitory_user = ForeignKey("self", PROTECT, null=True)

    # user timezone: default is set to be the timezone of executed server
    timezone = TimeZoneField()
    # default: get_full_name() returns 'First Last', but when this is true it returns 'Last First'
    is_full_name_reversed = BooleanField(default=False)

    flag_cooperate_on_research_anonymously = BooleanField(default=True)

    ################################################################
    # system settings

    objects = UserManager()

    EMAIL_FIELD = "email"
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = f"{APP_NAME}_users"

        verbose_name = _("user")
        verbose_name_plural = _("users")

    def clean(self) -> None:
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self) -> str:
        """
        Return the first_name plus the last_name, with a space in between.
        """
        if self.is_full_name_reversed:
            return f"{self.last_name} {self.first_name}".strip()
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        """Return the short name for the user."""
        return self.first_name

    def get_common_id_number(self) -> Optional[str]:
        """共通ID相当の情報があれば返す"""
        if self.is_faculty:
            return None
        if not isinstance(self.email, str) or not self.email.endswith(
            UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT
        ):
            raise ValueError(f"Invalid email address: id={self.id} ({self.email=})")
        common_id_number = self.email.split("@", 1)[0]
        try:
            validator = CommonIDNumberValidator()
            validator(common_id_number)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid email address: id={self.id} ({self.email=})"
            ) from exc
        return common_id_number

    @classmethod
    def build_email_from_common_id_number(cls, common_id_number: str) -> str:
        try:
            validator = CommonIDNumberValidator()
            validator(common_id_number)
        except ValidationError as exc:
            raise ValueError(f"Invalid common_id_number: {common_id_number})") from exc
        return common_id_number + UTOKYO_ECCS_MAIL_DOMAIN_WITH_AT

    def is_transitory(self) -> bool:
        """
        仮アカウント状態であるか

        仮アカウント状態であるユーザーは、仮アカウント向けのプロフィール画面のみ利用でき、そこから所定の情報を入力してはじめて有効なユーザーとなる
        """
        # 教員ユーザーは、現状の実装では仮アカウント状態になりえない
        if self.is_faculty:
            return False

        # 学生ユーザーは、所定の情報が設定されていない場合、仮アカウント状態である
        try:
            # 共通IDとの関連付け
            # ⇔ `email` が `{共通ID}@g.ecc.u-tokyo.ac.jp` の形式を満たしていない
            self.get_common_id_number()

        except ValueError:
            return True

        if self.is_transitory_user_via_google_auth():
            return True

        return False

    def is_transitory_user_via_google_auth(self) -> bool:
        """Google OAuth 経由での新規登録ユーザーであり、表示名等の必須設定がまだであるか"""
        # NOTE 表示名は入力必須であるので、既存ユーザーであれば必ず入力済みである
        return not bool(self.full_name)

    def is_google_auth_linked(self) -> bool:
        return self.google_id_info_sub is not None


class TransitoryUser(Model):
    "初期登録中の、正式にユーザーになる前の一時的なユーザー"

    class Meta:
        db_table = f"{APP_NAME}_transitory_users"
        indexes = (
            Index(fields=("email",)),
            Index(fields=("expired_at",)),
        )

    # NOTE class User との共通項目 ここから

    # Eメール。ログイン時に使用
    email_validator = EmailValidator()
    email = EmailField(
        _("email address"),
        help_text=_("Valid email address."),
        validators=[email_validator],
    )

    # 成績処理のために、学生証番号と氏名を記入させる。氏名表記は、ITC-LMSからのコピペを推奨する。
    full_name = CharField(_("full_name"), max_length=128, blank=True)

    # ハイフン込みで記入させてplags_frontないしクライアント側で形式（XX-XXXXXX）のvalidationを掛ける。
    # student_card_number_validator = ...  # 既に XXXXXXXX のデータが存在してしまっているので、クリーンアップするまで残す
    student_card_number = CharField(_("student card number"), max_length=32, blank=True)

    # 教員であるか
    is_faculty = BooleanField(default=False)

    # user that created this user
    invited_by = ForeignKey(
        User, PROTECT, related_name="invited_transitory_users", null=True, default=None
    )

    ################################################################
    # user configurable options

    # activation pin
    activation_pin = CharField(max_length=64)
    activated_at = DateTimeField(_("activated at"), null=True)

    # NOTE class User との共通項目 ここまで

    registered_at = DateTimeField(_("registered at"), auto_now_add=True)
    expired_at = DateTimeField()

    invited_organization = ForeignKey(
        "Organization",
        SET_NULL,
        related_name="invited_organization_for_transitory_users",
        null=True,
    )
    invited_course = ForeignKey(
        "Course",
        SET_NULL,
        related_name="invited_course_for_transitory_users",
        null=True,
    )
    invited_to_authority = UserAuthorityEnumField(null=True)

    def is_invitation_expired(self) -> bool:
        return self.expired_at <= get_current_datetime()


class SystemSetting(Model):
    class Meta:
        db_table = f"{APP_NAME}_system_settings"

    # foo = ...
    # foo_updated_at = DateTimeField(null=True)
    # foo_updated_by = ForeignKey(User, PROTECT, null=True, related_name='system_settings_foo_updated')

    use_login_page_notice = BooleanField(default=False)
    login_page_notice_title = TextField(max_length=250, default="")
    login_page_notice_text = TextField(max_length=4000, default="")
    use_login_page_notice_updated_at = DateTimeField(null=True)
    use_login_page_notice_updated_by = ForeignKey(
        User,
        PROTECT,
        null=True,
        related_name="system_settings_use_login_page_notice_updated",
    )
    login_page_notice_content_updated_at = DateTimeField(null=True)
    login_page_notice_content_updated_by = ForeignKey(
        User,
        PROTECT,
        null=True,
        related_name="system_settings_login_page_notice_content_updated",
    )

    email_sender_google_id_info_sub = CharField(max_length=255, null=True)
    email_sender_google_id_info_email_validator = EmailValidator()
    email_sender_google_id_info_email = EmailField(
        _("Google email address"),
        null=True,
        help_text=_("Valid google email address."),
        validators=[email_sender_google_id_info_email_validator],
    )
    email_sender_google_id_info_name = CharField(
        _("Google id name"), max_length=128, null=True
    )
    email_sender_google_id_info_picture = CharField(
        _("Google id picture"), max_length=128, null=True
    )
    email_sender_google_credentials_json_str = CharField(
        _("Google oauth credentials"), max_length=4096, null=True
    )
    email_sender_updated_at = DateTimeField(null=True)
    email_sender_updated_by = ForeignKey(
        User, PROTECT, null=True, related_name="system_settings_email_sender_updated"
    )

    email_to_address_override_enabled = BooleanField(default=False)
    email_to_address_override_email_validator = EmailValidator()
    email_to_address_override_email = EmailField(
        null=True,
        help_text=_("Valid email address."),
        validators=[email_to_address_override_email_validator],
    )
    email_to_address_override_updated_at = DateTimeField(null=True)
    email_to_address_override_updated_by = ForeignKey(
        User,
        PROTECT,
        null=True,
        related_name="system_settings_email_to_address_override_updated",
    )


class Organization(Model):
    # dimension
    name = CharField(max_length=64, unique=True, db_index=True)

    class Meta:
        db_table = f"{APP_NAME}_organizations"

    # constant
    created_at = DateTimeField(auto_now_add=True)
    created_by = ForeignKey(User, PROTECT, related_name="organizations_created")

    # modifiable
    is_active = BooleanField()
    is_active_updated_by = ForeignKey(
        User, PROTECT, related_name="organizations_is_active_updated"
    )
    is_active_updated_at = DateTimeField(auto_now_add=True)


class OrganizationUser(Model):
    # dimension
    organization = ForeignKey(Organization, PROTECT)
    user = ForeignKey(User, PROTECT, related_name="of_organizations")

    class Meta:
        db_table = f"{APP_NAME}_organization_users"
        unique_together = (("organization", "user"),)

    # constant
    added_at = DateTimeField(auto_now_add=True)
    added_by = ForeignKey(User, PROTECT, related_name="added_organization_users")

    # modifiable
    is_active = BooleanField()
    is_active_updated_at = DateTimeField(auto_now_add=True)
    is_active_updated_by = ForeignKey(
        User, PROTECT, related_name="organization_users_is_active_updated"
    )

    authority = UserAuthorityEnumField()
    authority_updated_at = DateTimeField(auto_now_add=True)
    authority_updated_by = ForeignKey(
        User, PROTECT, related_name="organization_users_authority_updated"
    )


##############################################################
# Course
# * insert manual: Course => Course*History => Course*
# * sub-course level: Course => ** => Exercise
##############################################################


class CourseDescriptionMethodEnum(ChoosableEnum):
    BY_CONCRETE = "by_concrete"
    BY_FIELD = "by_field"

    def by_concrete(self) -> bool:
        return self == self.BY_CONCRETE

    def by_field(self) -> bool:
        return self == self.BY_FIELD


def random_key_generator() -> bytes:
    return secrets.token_bytes(32)


class Course(Model):
    # dimension
    organization = ForeignKey(
        Organization, PROTECT, related_name="courses_of_organization"
    )
    name = CharField(max_length=64, db_index=True)

    class Meta:
        db_table = f"{APP_NAME}_courses"
        unique_together = (("organization", "name"),)

    # constant
    created_at = DateTimeField(auto_now_add=True)
    created_by = ForeignKey(User, PROTECT, related_name="courses_created")

    submission_parcel_id_encryption_key = BinaryField(default=random_key_generator)
    submission_id_encryption_key = BinaryField(default=random_key_generator)
    evaluation_id_encryption_key = BinaryField(default=random_key_generator)
    trial_evaluation_id_encryption_key = BinaryField(default=random_key_generator)
    custom_evaluation_tag_id_encryption_key = BinaryField(default=random_key_generator)

    # modifiable
    is_active = BooleanField()
    is_active_updated_at = DateTimeField(auto_now_add=True)
    is_active_updated_by = ForeignKey(
        User, PROTECT, related_name="courses_is_active_updated"
    )


    default_lang_i18n = CharField(max_length=16, default="ja")
    title = CharField(max_length=128)
    body = TextField(max_length=65536)

    exercise_default_begins_at = DateTimeField()
    exercise_default_opens_at = DateTimeField()
    exercise_default_checks_at = DateTimeField(null=True)
    exercise_default_closes_at = DateTimeField()
    exercise_default_ends_at = DateTimeField()

    exercise_default_is_shared_after_confirmed = BooleanField(default=False)
    exercise_default_score_visible_from = UserAuthorityEnumField(
        default=UserAuthorityEnum.LECTURER
    )
    exercise_default_remarks_visible_from = UserAuthorityEnumField(
        default=UserAuthorityEnum.LECTURER
    )

    edited_at = DateTimeField(auto_now_add=True)
    edited_by = ForeignKey(User, PROTECT, related_name="courses_edited")

    is_registerable = BooleanField(default=True)

    ################################################################
    # ユーザー向け設定

    # course/top に表示できる「おしらせ」
    feature_use_course_top_notice = BooleanField(default=False)
    feature_course_top_notice_title = TextField(max_length=250, default="")
    feature_course_top_notice_text = TextField(max_length=4000, default="")

    # テンプレートにおける exercise との互換用
    def calculated_begins_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        try:
            earliest_exercise: Exercise = (
                self.exercises_of_course.filter(begins_at__isnull=False)
                .only("begins_at", "name")
                .earliest("begins_at")
            )
            earliest_begins_at = earliest_exercise.begins_at
            if earliest_begins_at is None:
                return (self.exercise_default_begins_at, "default")
            return min(
                (self.exercise_default_begins_at, "default"),
                (earliest_begins_at, f"exercise:{earliest_exercise.name}"),
            )
        except Exercise.DoesNotExist:
            return (self.exercise_default_begins_at, "default")

    def calculated_opens_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        try:
            earliest_exercise: Exercise = (
                self.exercises_of_course.filter(opens_at__isnull=False)
                .only("opens_at", "name")
                .earliest("opens_at")
            )
            earliest_opens_at = earliest_exercise.opens_at
            if earliest_opens_at is None:
                return (self.exercise_default_opens_at, "default")
            return min(
                (self.exercise_default_opens_at, "default"),
                (earliest_opens_at, f"exercise:{earliest_exercise.name}"),
            )
        except Exercise.DoesNotExist:
            return (self.exercise_default_opens_at, "default")

    def calculated_closes_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        try:
            latest_exercise: Exercise = (
                self.exercises_of_course.filter(closes_at__isnull=False)
                .only("closes_at", "name")
                .latest("closes_at")
            )
            latest_closes_at = latest_exercise.closes_at
            if latest_closes_at is None:
                return (self.exercise_default_closes_at, "default")
            return max(
                (self.exercise_default_closes_at, "default"),
                (latest_closes_at, f"exercise:{latest_exercise.name}"),
            )
        except Exercise.DoesNotExist:
            return (self.exercise_default_closes_at, "default")

    def calculated_ends_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        try:
            latest_exercise: Exercise = (
                self.exercises_of_course.filter(ends_at__isnull=False)
                .only("ends_at", "name")
                .latest("ends_at")
            )
            latest_ends_at = latest_exercise.ends_at
            if latest_ends_at is None:
                return (self.exercise_default_ends_at, "default")
            return max(
                (self.exercise_default_ends_at, "default"),
                (latest_ends_at, f"exercise:{latest_exercise.name}"),
            )
        except Exercise.DoesNotExist:
            return (self.exercise_default_ends_at, "default")

    def calculated_begins_at(self) -> datetime.datetime:
        return self.calculated_begins_at_with_origin()[0]

    def calculated_opens_at(self) -> datetime.datetime:
        return self.calculated_opens_at_with_origin()[0]

    def calculated_closes_at(self) -> datetime.datetime:
        return self.calculated_closes_at_with_origin()[0]

    def calculated_ends_at(self) -> datetime.datetime:
        return self.calculated_ends_at_with_origin()[0]

    def begins(self) -> bool:
        return self.calculated_begins_at() <= get_current_datetime()

    def begins_to_ends(self) -> bool:
        return (
            self.calculated_begins_at()
            <= get_current_datetime()
            < self.calculated_ends_at()
        )

    def ends(self) -> bool:
        return self.calculated_ends_at() <= get_current_datetime()

    def opens(self) -> bool:
        return self.calculated_opens_at() <= get_current_datetime()

    def opens_to_closes(self) -> bool:
        return (
            self.calculated_opens_at()
            <= get_current_datetime()
            < self.calculated_closes_at()
        )

    def closes(self) -> bool:
        return self.calculated_closes_at() <= get_current_datetime()


class CourseTopNoticeByOrganization(Model):
    "組織単位で共通のメッセージを、配下のコーストップ画面に表示する機能"

    class Meta:
        db_table = f"{APP_NAME}_course_top_notices_by_organization"

    organization = ForeignKey(Organization, PROTECT)

    # constant
    added_at = DateTimeField(auto_now_add=True)
    added_by = ForeignKey(
        User, PROTECT, related_name="added_course_top_notices_by_organization"
    )

    # modifiable
    title = TextField(max_length=250)
    text = TextField(max_length=4000)
    # in JSON format (Array<int>)
    target_course_name_list = TextField(max_length=4000)
    is_public_to_students = BooleanField()

    last_edited_at = DateTimeField(auto_now=True)
    last_edited_by = ForeignKey(
        User, PROTECT, related_name="last_edited_course_top_notices_by_organization"
    )



class CourseUser(Model):
    # dimension
    course = ForeignKey(Course, PROTECT, related_name="users")
    user = ForeignKey(User, PROTECT, related_name="of_courses")

    class Meta:
        db_table = f"{APP_NAME}_course_users"
        unique_together = (("course", "user"),)

    # constant
    added_at = DateTimeField(auto_now_add=True)
    added_by = ForeignKey(User, PROTECT, related_name="added_course_users")

    # modifiable
    is_active = BooleanField()
    is_active_updated_at = DateTimeField(auto_now_add=True)
    is_active_updated_by = ForeignKey(
        User, PROTECT, related_name="course_users_is_active_updated"
    )

    authority = UserAuthorityEnumField()
    authority_updated_at = DateTimeField(auto_now_add=True)
    authority_updated_by = ForeignKey(
        User, PROTECT, related_name="course_users_authority_updated"
    )

    # NOTE added for review assign notification
    slack_webhook_url = CharField(max_length=255, null=True)
    slack_user_id = CharField(max_length=63, null=True)


class CustomEvaluationTag(Model):
    class Meta:
        db_table = f"{APP_NAME}_custom_evaluation_tags"
        unique_together = (("organization", "course", "code"),)

    organization = ForeignKey(Organization, PROTECT)
    course = ForeignKey(Course, PROTECT)

    activeness = ActivenessField(default=ActivenessEnum.ACTIVE)
    activeness_updated_at = DateTimeField(auto_now_add=True)
    activeness_updated_by = ForeignKey(
        User, PROTECT, related_name="custom_evaluation_tags_activeness_updated"
    )

    code = CharField(max_length=16)
    description = CharField(max_length=250)

    color = CharField(max_length=16)
    background_color = CharField(max_length=16)

    is_visible_to_students = BooleanField()

    created_at = DateTimeField(auto_now_add=True)
    created_by = ForeignKey(
        User, PROTECT, related_name="custom_evaluation_tags_created"
    )
    updated_at = DateTimeField(auto_now=True)
    updated_by = ForeignKey(
        User, PROTECT, related_name="custom_evaluation_tags_updated"
    )


# NOTE 将来ちゃんとしたインポート機能を作る時用


# def get_course_settings_import_file_upload_path(instance: Model, exercise_form_file: str) -> str:
#     return os.path.join(
#         settings.BASE_APP_DATA_DIR if settings.DEBUG else "",
#         DATABASE_EXERCISE_FORM_FILE_ROOT_PATH,
#         str(instance.id),
#         exercise_form_file,
#     )


# class CourseSettingsImportFile(Model):
#     class Meta:
#         db_table = f"{APP_NAME}_course_settings_import_files"

#     organization = ForeignKey(Organization, PROTECT)
#     course = ForeignKey(Course, PROTECT)

#     course_settings_import_file = FileField(
#         upload_to=get_course_settings_import_file_upload_path, null=True, max_length=250
#     )
#     course_settings_import_file_initial_name = CharField(max_length=255, null=True)

#     # modifiable
#     is_valid = BooleanField(null=True)
#     verified_at = DateTimeField(null=True)

#     applied_count = IntegerField(default=0)
#     last_applied_at = DateTimeField(null=True)

#     # system managed
#     created_at = DateTimeField(auto_now_add=True)
#     created_by = ForeignKey(User, PROTECT, related_name="course_settings_import_files_created")
#     updated_at = DateTimeField(auto_now=True)
#     updated_by = ForeignKey(User, PROTECT, related_name="course_settings_import_files_updated")


# class CourseSettingsImportHistory(Model):
#     class Meta:
#         db_table = f"{APP_NAME}_course_settings_import_histories"

#     organization = ForeignKey(Organization, PROTECT)
#     course = ForeignKey(Course, PROTECT)

#     course_settings_import_file = ForeignKey(CourseSettingsImportFile, PROTECT)

#     # system managed
#     created_at = DateTimeField(auto_now_add=True)
#     created_by = ForeignKey(User, PROTECT, related_name="course_settings_import_histories_created")
#     updated_at = DateTimeField(auto_now=True)
#     updated_by = ForeignKey(User, PROTECT, related_name="course_settings_import_histories_updated")


def get_develop_file_storage_file_upload_path(
    instance: Model, develop_file_storage_filename: str
) -> str:
    return os.path.join(
        settings.BASE_APP_DATA_DIR if settings.DEBUG else "",
        DATABASE_DEVELOP_FILE_ROOT_PATH,
        "_".join((str_of_int_sort_safe(instance.id), develop_file_storage_filename)),
    )


class DevelopFileStorage(Model):
    develop_file = FileField(
        upload_to=get_develop_file_storage_file_upload_path, null=True, max_length=250
    )


def _build_tree_path_text_choice(path_spec: str) -> Tuple[str, str]:
    "木構造の表現を文字列に押し込む機構"
    # NOTE path配下に対して prefix match で絞り込みたいという需要がある
    #     IDEA "-" を末尾に挿入することで prefix collision への対策とする
    assert "-" not in path_spec, f"hyphen (-) not allowed in path_spec: {path_spec!r}"
    path = path_spec.split("__")
    value = "".join(node + "-" for node in path)
    name = " > ".join(path)
    return (value, name)


# NOTE 短縮のためのエイリアス
_btptc = _build_tree_path_text_choice


class OperationLog(Model):
    "操作ログ"

    @enum.unique
    class OperationRole(TextChoices):
        ADMINISTRATOR = ("administrator", "administrator")

        ORGANIZATION_MANAGER = ("o_manager", "o_manager")
        ORGANIZATION_LECTURER = ("o_lecturer", "o_lecturer")

        COURSE_MANAGER = ("c_manager", "c_manager")
        COURSE_LECTURER = ("c_lecturer", "c_lecturer")
        COURSE_ASSISTANT = ("c_assistant", "c_assistant")
        COURSE_STUDENT = ("c_student", "c_student")

    @enum.unique
    class OperationType(TextChoices):
        INVITE_USER = _btptc("INVITE_USER")
        INVITE_USER__RESEND_ACTIVATION_PIN = _btptc(
            "INVITE_USER__RESEND_ACTIVATION_PIN"
        )
        INVITE_USER_TO_ORGANIZATION = _btptc("INVITE_USER_TO_ORGANIZATION")
        INVITE_USER_TO_ORGANIZATION__RESEND_ACTIVATION_PIN = _btptc(
            "INVITE_USER_TO_ORGANIZATION__RESEND_ACTIVATION_PIN"
        )

    organization = ForeignKey(Organization, PROTECT, null=True)
    course = ForeignKey(Course, PROTECT, null=True)

    operated_at = DateTimeField(auto_now_add=True)
    operated_by = ForeignKey(User, PROTECT)

    # 何のロールとして操作を実行したか
    operation_role = CharField(max_length=64, choices=OperationRole.choices)
    # どの種類の操作を実行したか
    operation_type = CharField(max_length=64, choices=OperationType.choices)
    # operation_type に対する追加情報 JSON?
    operation_details = CharField(max_length=4000, default="{}")

    class Meta:
        db_table = f"{APP_NAME}_operation_logs"

        indexes = (
            Index(
                fields=(
                    "organization",
                    "course",
                    "operated_at",
                )
            ),
            Index(
                fields=(
                    "organization",
                    "course",
                    "operated_by",
                )
            ),
            Index(fields=("operated_at",)),
        )


def get_job_outcome_file_upload_path(instance: Model, job_outcome_filename: str) -> str:
    return os.path.join(
        settings.BASE_APP_DATA_DIR if settings.DEBUG else "",
        DATABASE_JOB_OUTCOME_FILE_ROOT_PATH,
        "_".join((str(instance.id), job_outcome_filename)),
    )


class AsyncJobBase(Model):
    job_type: str = CharField(max_length=250)
    job_options: str = CharField(max_length=4000)

    job_started_at: datetime.datetime = DateTimeField(null=True)
    job_finished_at: datetime.datetime = DateTimeField(null=True)

    class JobStatus(TextChoices):
        WAITING = "WAITING", _("JobStatus_WAITING")
        ONGOING = "ONGOING", _("JobStatus_ONGOING")
        SUCCEEDED = "SUCCEEDED", _("JobStatus_SUCCEEDED")
        FAILED = "FAILED", _("JobStatus_FAILED")
        CANCELLED = "CANCELLED", _("JobStatus_CANCELLED")
        STOPPED = "STOPPED", _("JobStatus_STOPPED")
        KILLED = "KILLED", _("JobStatus_KILLED")
        UNKNOWN = "UNKNOWN", _("JobStatus_UNKNOWN")

    job_status = CharField(
        max_length=16,
        choices=JobStatus.choices,
        default=JobStatus.WAITING,
    )

    class JobOutcomeType(TextChoices):
        NOTHING = "NOTHING", _("JobOutcomeType_NOTHING")
        FILE = "FILE", _("JobOutcomeType_FILE")
        TEXT = "TEXT", _("JobOutcomeType_TEXT")

    job_outcome_type = CharField(
        max_length=16,
        choices=JobOutcomeType.choices,
        default=JobOutcomeType.NOTHING,
    )

    job_outcome_file = FileField(
        upload_to=get_job_outcome_file_upload_path, max_length=250, null=True
    )
    job_outcome_filename = CharField(max_length=250, null=True)
    job_outcome_text = CharField(max_length=4000, null=True, default=None)

    class Meta:
        abstract = True


class CourseAsyncJob(AsyncJobBase):
    # dimension
    organization = ForeignKey(Organization, PROTECT)
    course = ForeignKey(Course, PROTECT)

    executed_at = DateTimeField(auto_now_add=True)
    executed_by = ForeignKey(User, PROTECT)

    class Meta:
        db_table = f"{APP_NAME}_course_async_jobs"

        indexes = (
            Index(
                fields=(
                    "organization",
                    "course",
                    "job_type",
                )
            ),
            Index(fields=("job_type",)),
        )


class CourseAsyncJobProgressLog(Model):
    "進捗ログ"
    # 更新は行われない想定のデーブル
    job = ForeignKey(CourseAsyncJob, CASCADE)

    progress_ppm = IntegerField()
    created_at = DateTimeField(auto_now_add=True)

    class Meta:
        db_table = f"{APP_NAME}_course_async_job_progress_logs"


##############################################################
# Exercise
# * sub-exercise level: Exercise => ** => Submission
##############################################################


class ExerciseDescriptionMethodEnum(ChoosableEnum):
    BY_CONCRETE = "by_concrete"
    BY_FIELD = "by_field"

    def by_concrete(self) -> bool:
        return self == self.BY_CONCRETE

    def by_field(self) -> bool:
        return self == self.BY_FIELD


def get_exercise_form_file_upload_path(instance: Model, exercise_form_file: str) -> str:
    del instance, exercise_form_file
    raise NotImplementedError
    # return os.path.join(
    #     settings.BASE_APP_DATA_DIR if settings.DEBUG else "",
    #     DATABASE_EXERCISE_FORM_FILE_ROOT_PATH,
    #     str(instance.id),
    #     exercise_form_file,
    # )


class Exercise(Model):
    # dimension
    course = ForeignKey(Course, PROTECT, related_name="exercises_of_course")
    name = CharField(max_length=64, db_index=True)

    class Meta:
        db_table = f"{APP_NAME}_exercises"
        unique_together = (("course", "name"),)

    # constant
    created_at = DateTimeField(auto_now_add=True)
    created_by = ForeignKey(User, PROTECT, related_name="exercises_created")

    # modifiable
    # 自動評価つき課題であるか Falseなら as-is
    is_autograde = BooleanField(default=False)
    # can be git hash (md5) of directory, timestamp string or else
    latest_version = CharField(max_length=64, db_index=True, blank=True)

    # ### if is_autograde
    latest_concrete_hash = CharField(max_length=64, db_index=True, null=True)

    default_lang_i18n = CharField(max_length=16, default="ja")

    title = CharField(max_length=128)
    # expected to be "Jupyter Notebook (ipynb) JSON" format
    body_ipynb_json = TextField(max_length=65536, null=True)

    drive_resource_id = TextField(max_length=256, null=True)

    begins_at = DateTimeField(null=True)
    opens_at = DateTimeField(null=True)
    checks_at = DateTimeField(null=True)
    closes_at = DateTimeField(null=True)
    ends_at = DateTimeField(null=True)

    is_shared_after_confirmed = BooleanField(null=True, default=None)
    score_visible_from = UserAuthorityEnumField(null=True, default=None)
    remarks_visible_from = UserAuthorityEnumField(null=True, default=None)
    is_draft = BooleanField(default=False)

    # トライアル提出の有効フラグ
    is_trial_enabled = BooleanField()
    # トライアル環境でのエディタ（現状codemirrorのみ）の設定など
    trial_initial_source = CharField(max_length=4000)
    trial_editor_name = CharField(max_length=250, default="CodeMirror")
    # JSON文字列形式
    trial_editor_options = CharField(max_length=4000, null=True, default=None)

    edited_at = DateTimeField(auto_now_add=True)
    edited_by = ForeignKey(User, PROTECT, related_name="exercises_edited")

    # テンプレートにおける exercise との互換用
    def calculated_begins_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        return calculate_begins_at_with_origin(
            self.begins_at, lambda: self.course.exercise_default_begins_at
        )

    def calculated_opens_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        opens_at_with_origin = calculate_opens_at_with_origin(
            self.opens_at, lambda: self.course.exercise_default_opens_at
        )
        begins_at = self.calculated_begins_at()
        if opens_at_with_origin[0] < begins_at:
            return (begins_at, "superseded by Begin")
        return opens_at_with_origin

    def calculated_checks_at_with_origin(
        self,
    ) -> Tuple[Optional[datetime.datetime], DeadlineOrigin]:
        return calculate_checks_at_with_origin(
            self.checks_at, lambda: self.course.exercise_default_checks_at
        )

    def calculated_closes_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        closes_at_with_origin = calculate_closes_at_with_origin(
            self.closes_at, lambda: self.course.exercise_default_closes_at
        )
        ends_at = self.calculated_ends_at()
        if closes_at_with_origin[0] > ends_at:
            return (ends_at, "superseded by End")
        return closes_at_with_origin

    def calculated_ends_at_with_origin(
        self,
    ) -> Tuple[datetime.datetime, DeadlineOrigin]:
        return calculate_ends_at_with_origin(
            self.ends_at, lambda: self.course.exercise_default_ends_at
        )

    def calculated_begins_at(self) -> datetime.datetime:
        return self.calculated_begins_at_with_origin()[0]

    def calculated_opens_at(self) -> datetime.datetime:
        return self.calculated_opens_at_with_origin()[0]

    def calculated_checks_at(self) -> Optional[datetime.datetime]:
        return self.calculated_checks_at_with_origin()[0]

    def calculated_closes_at(self) -> datetime.datetime:
        return self.calculated_closes_at_with_origin()[0]

    def calculated_ends_at(self) -> datetime.datetime:
        return self.calculated_ends_at_with_origin()[0]

    def begins(self) -> bool:
        return self.calculated_begins_at() <= get_current_datetime()

    def begins_to_ends(self) -> bool:
        return (
            self.calculated_begins_at()
            <= get_current_datetime()
            < self.calculated_ends_at()
        )

    def ends(self) -> bool:
        return self.calculated_ends_at() <= get_current_datetime()

    def opens(self) -> bool:
        return self.calculated_opens_at() <= get_current_datetime()

    def opens_to_closes(self) -> bool:
        return (
            self.calculated_opens_at()
            <= get_current_datetime()
            < self.calculated_closes_at()
        )

    def closes(self) -> bool:
        return self.calculated_closes_at() <= get_current_datetime()

    # def checks(self) -> bool:
    #     return self.calculated_checks_at() <= get_current_datetime()

    # def opens_to_checks(self):
    #     return self.calculated_opens_at() <= get_current_datetime() < self.calculated_checks_at()

    # def checks_to_closes(self) -> bool:
    #     return self.calculated_checks_at() <= get_current_datetime() < self.calculated_closes_at()

    def closes_to_ends(self) -> bool:
        return (
            self.calculated_closes_at()
            <= get_current_datetime()
            < self.calculated_ends_at()
        )

    def is_published(self) -> bool:
        return not self.is_draft and self.begins_to_ends()

    def calculated_is_shared_after_confirmed(self) -> bool:
        if self.is_shared_after_confirmed is not None:
            return self.is_shared_after_confirmed
        return self.course.exercise_default_is_shared_after_confirmed

    def calculated_is_shared_after_confirmed_display_value(self) -> str:
        # NOTE IsSharedAfterConfirmedEnum.to_choices と実装一貫性を保つこと
        if self.is_shared_after_confirmed is not None:
            return "Yes" if self.is_shared_after_confirmed else "No"
        current_default_str = (
            "Yes" if self.course.exercise_default_is_shared_after_confirmed else "No"
        )
        return f"Default (current: {current_default_str})"

    def calculated_score_visible_from(self) -> UserAuthorityEnum:
        if self.score_visible_from is not None:
            return self.score_visible_from
        return self.course.exercise_default_score_visible_from

    def calculated_score_visible_from_display_value(self) -> str:
        # NOTE ScoreVisibleFromEnum.to_exercise_choices と実装一貫性を保つこと
        if self.score_visible_from is not None:
            return UserAuthorityEnum(self.score_visible_from).to_display_name()
        current_default_str = UserAuthorityEnum(
            self.course.exercise_default_score_visible_from
        ).to_display_name()
        return f"Default (current: {current_default_str})"

    def calculated_remarks_visible_from(self) -> UserAuthorityEnum:
        if self.remarks_visible_from is not None:
            return self.remarks_visible_from
        return self.course.exercise_default_remarks_visible_from

    def calculated_remarks_visible_from_display_value(self) -> str:
        # NOTE RemarksVisibleFromEnum.to_exercise_choices と実装一貫性を保つこと
        if self.remarks_visible_from is not None:
            return UserAuthorityEnum(self.remarks_visible_from).to_display_name()
        current_default_str = UserAuthorityEnum(
            self.course.exercise_default_remarks_visible_from
        ).to_display_name()
        return f"Default (current: {current_default_str})"


class ExerciseVersion(Model):
    """
    Exerciseの登録で再登録が発生しないように、全てのバージョンを記録する

    ATTENTION Exercise.version との整合性は実装による保証のみ
    """

    # dimension
    exercise = ForeignKey(Exercise, PROTECT, related_name="versions_of_exercise")
    version = CharField(max_length=64, db_index=True)

    class Meta:
        db_table = f"{APP_NAME}_exercise_versions"
        unique_together = (("exercise", "version"),)

    # constant
    created_at = DateTimeField(auto_now_add=True)
    created_by = ForeignKey(User, PROTECT, related_name="exercise_versions_created")


##############################################################
# Submission
# * Structure: SubmissionParcel => Submission(+exercise)
##############################################################


class SubmissionFormatEnum(ChoosableEnum):
    JUPYTER_NOTEBOOK = "jupyter_notebook"
    PYTHON_SOURCE = "python_source"

    def jupyter_notebook(self) -> bool:
        return self == self.JUPYTER_NOTEBOOK

    def python_source(self) -> bool:
        return self == self.PYTHON_SOURCE


class SubmissionTypeEnum:
    # 10: 通常の提出
    NORMAL = 10
    # 20: トライアル提出
    TRIAL = 20
    # 70: システムによる試験提出
    SYSTEM = 70


def SubmissionFormatEnumField(**kwargs: Any) -> CharField:  # type:ignore[type-arg]
    return ChoosableEnumField(SubmissionFormatEnum, **kwargs)


def SubmissionTypeEnumField(**kwargs: Any) -> IntegerField:  # type:ignore[type-arg]
    return ChoosableIntegerEnumField(SubmissionTypeEnum, **kwargs)


def get_submission_parcel_file_upload_path(
    instance: Model, submission_parcel_file: str
) -> str:
    return os.path.join(
        settings.BASE_APP_DATA_DIR if settings.DEBUG else "",
        DATABASE_SUBMISSION_PARCEL_FILE_ROOT_PATH,
        str(instance.id),
        submission_parcel_file,
    )


def get_submission_file_upload_path(instance: Model, submission_file: str) -> str:
    return os.path.join(
        settings.BASE_APP_DATA_DIR if settings.DEBUG else "",
        DATABASE_SUBMISSION_FILE_ROOT_PATH,
        str(instance.id),
        submission_file,
    )


class SubmissionParcel(Model):
    """
    複数のSubmissionをまとめて行う提出単位

    学生にとっての提出一覧画面と紐づく単位
    複数の小問を含む課題を想定する

    zipファイルなどで複数の提出をいっぺんに行うようなものは想定しない
    あくまで「学生側としては一つの課題への提出」であるようなものにのみ適用する
    """

    # input
    organization = ForeignKey(Organization, PROTECT)
    course = ForeignKey(Course, PROTECT)

    submitted_at = DateTimeField(auto_now_add=True)
    submitted_by = ForeignKey(User, PROTECT)
    submission_parcel_file = FileField(
        upload_to=get_submission_parcel_file_upload_path, max_length=250
    )
    submission_parcel_file_initial_name = CharField(max_length=255, null=True)
    submission_colaboratory_url = CharField(max_length=2047, null=True)

    class Meta:
        db_table = f"{APP_NAME}_submission_parcels"

        indexes = (
            # 教員の全提出物一覧画面（コース配下の全提出を、最新提出順に）
            # ... WHERE course = ? ORDER BY submitted_at DESC
            Index(
                fields=(
                    "organization",
                    "course",
                    "-submitted_at",
                )
            ),
            # 学生の提出物一覧画面（自分の提出全てを、最新提出順に）
            # ... WHERE course = ? AND submitted_by = ? ORDER BY submitted_at DESC
            Index(
                fields=(
                    "organization",
                    "course",
                    "submitted_by",
                    "-submitted_at",
                )
            ),
        )


class Submission(Model):
    # input
    organization = ForeignKey(Organization, PROTECT)
    course = ForeignKey(Course, PROTECT)
    submission_parcel = ForeignKey(SubmissionParcel, PROTECT, null=True)
    exercise = ForeignKey(Exercise, PROTECT)
    exercise_version = CharField(max_length=64, db_index=True, blank=True)
    exercise_concrete_hash = CharField(max_length=64, db_index=True, null=True)
    # ATTENTION: #292 以前は Exercise.is_autograde が不変であったが、以降は可変になるので、
    #            exercise_version などと同様に「提出時点での」 Exercise.is_autograde の値を保持する。
    is_autograded_exercise = BooleanField(default=False)

    submitted_at = DateTimeField(default=get_current_datetime)
    submitted_by = ForeignKey(User, PROTECT)
    submission_file = FileField(
        upload_to=get_submission_file_upload_path, max_length=250
    )
    submission_format = SubmissionFormatEnumField(
        default=SubmissionFormatEnum(SubmissionFormatEnum.PYTHON_SOURCE).value
    )
    submission_type = SubmissionTypeEnumField(default=SubmissionTypeEnum.NORMAL)

    # 再評価により生成された提出について、その元となった提出を保持
    rejudge_original_submission = ForeignKey(
        "Submission", PROTECT, null=True, related_name="submissions_rejudge_replicated"
    )
    rejudge_deep_original_submission = ForeignKey(
        "Submission",
        PROTECT,
        null=True,
        related_name="submissions_rejudge_depp_replicated",
    )
    rejudge_deep_original_submission_parcel = ForeignKey(
        SubmissionParcel,
        PROTECT,
        null=True,
        related_name="submission_parcels_rejudge_depp_replicated",
    )
    rejudge_requested_at = DateTimeField(null=True)
    rejudge_requested_by = ForeignKey(
        User, PROTECT, null=True, related_name="submissions_rejudge_requested"
    )

    class Meta:
        db_table = f"{APP_NAME}_submissions"

        indexes = (
            # 教員の全提出物一覧画面（コース配下の全提出を、最新提出順に）
            # ... WHERE course = ? AND submission_type = NORMAL ORDER BY submitted_at DESC
            Index(
                fields=(
                    "organization",
                    "course",
                    "submission_type",
                    "-submitted_at",
                )
            ),
            # 教員の課題別提出物一覧画面（コース配下の特定課題の提出を、最新提出順に）
            # ... WHERE course = ? AND submission_type = NORMAL ORDER BY submitted_at DESC
            Index(
                fields=(
                    "organization",
                    "course",
                    "exercise",
                    "submission_type",
                    "-submitted_at",
                )
            ),
            # 学生の提出物一覧画面（自分の提出全てを、最新提出順に）
            # ... WHERE course = ? AND submitted_by = ? ORDER BY submitted_at DESC
            Index(
                fields=(
                    "organization",
                    "course",
                    "submitted_by",
                    "-submitted_at",
                )
            ),
        )

    # state
    # NOTE 最新提出フラグは SubmissionTypeEnum.NORMAL 内での利用を想定する。
    # ATTENTION このフラグは結果整合的キャッシュとして取り扱い、更新する。
    #     cf. cls.update_latest_flag_eventually()
    # ATTENTION 一時的に、複数の提出に対して最新フラグが立つ場合がある。（結果整合性）
    #     NOTE そのかわり、最新の提出には必ずフラグが立つ。
    # FUTURE いずれ window function あたりでキャッシュなしで解決したい...
    is_latest_submission = BooleanField(default=True)

    # lecturer
    is_lecturer_evaluation_confirmed = BooleanField(default=False)
    confirmed_at = DateTimeField(null=True)
    confirmed_by = ForeignKey(
        User, PROTECT, null=True, related_name="submissions_confirmed"
    )

    lecturer_grade = IntegerField(null=True)
    lecturer_comment = CharField(max_length=4095, default="")
    lecturer_comment_updated_at = DateTimeField(null=True)
    lecturer_comment_updated_by = ForeignKey(
        User, PROTECT, null=True, related_name="submissions_lecturer_comment_updated"
    )

    # ATTENTION deprecated on v2.1.0
    # NOTE migrate data to reviewer_remarks (True -> "Marked for criticism")
    is_marked_for_criticism = BooleanField(default=False)
    marked_for_criticism_by = ForeignKey(
        User, PROTECT, null=True, related_name="submissions_marked_for_criticism"
    )

    reviewer_remarks = CharField(max_length=4095, default="")
    reviewer_remarks_updated_at = DateTimeField(null=True)
    reviewer_remarks_updated_by = ForeignKey(
        User, PROTECT, null=True, related_name="submissions_reviewer_remarks_updated"
    )

    # deprecated ?
    lecturer_assigned = ForeignKey(
        User, PROTECT, null=True, related_name="submissions_assigned"
    )

    # autograde only
    # once handshaked with judge
    external_submission_id = IntegerField(null=True)

    # judge progress
    evaluation_queued_at = DateTimeField(null=True)
    evaluation_progress_percent = IntegerField(null=True)

    # judge result
    evaluated_at = DateTimeField(null=True)
    evaluation_result_json = TextField(max_length=65535, null=True)
    # judge result cache (part of evaluation_result_json)
    overall_grade = IntegerField(null=True)
    overall_status = TextField(max_length=1023, null=True)
    observed_statuses = TextField(max_length=4095, null=True)

    def is_evaluated(self) -> bool:
        return bool(self.evaluated_at)

    def is_submission_delayed(self) -> bool:
        deadline = (
            self.exercise.calculated_checks_at() or self.exercise.calculated_closes_at()
        )
        return self.submitted_at >= deadline

    def update_latest_flag_eventually(self) -> None:
        """最新提出フラグ `self.is_latest_submission` の結果整合的更新

        - ATTENTION Submission レコードの作成してから呼び出すこと。
        """
        max_retry = 3
        for trial_idx in range(max_retry):
            try:
                Submission.objects.filter(
                    exercise=self.exercise,
                    submitted_by=self.submitted_by,
                    is_latest_submission=True,
                    id__lt=self.id,
                ).update(is_latest_submission=False)
                return
            except Exception:  # pylint: disable=broad-except
                retrying = trial_idx + 1 == max_retry
                next_action_message = (
                    f"Trial #{trial_idx+1}, waiting for retry"
                    if retrying
                    else "aborting"
                )
                SLACK_NOTIFIER.warning(
                    "On: app_front.utils.submission_util.insert_submission()\n"
                    f'Issue: "Latest submission" flag update failed ({next_action_message})\n',
                    tracebacks=traceback.format_exc(),
                )


class EmailHistory(Model):
    class Meta:
        db_table = f"{APP_NAME}_email_histories"

    organization = ForeignKey(Organization, PROTECT, null=True)  # null means "by admin"
    course = ForeignKey(Course, PROTECT, null=True)
    to_user = ForeignKey(User, PROTECT, related_name="of_email_histories", null=True)
    to_transitory_user = ForeignKey(
        TransitoryUser, PROTECT, related_name="of_email_histories", null=True
    )
    objective = CharField(max_length=64)

    from_address = EmailField()
    to_address = TextField(max_length=4095)  # EmailField だと複数宛先で死ぬ ', '.join(addrs)
    subject = CharField(max_length=256)
    content_plain = TextField(max_length=65535)
    content_html = TextField(max_length=65535, null=True)
    sent_at = DateTimeField(auto_now_add=True)

    smtp_successful = BooleanField(default=True)
    smtp_traceback = TextField(max_length=65535, null=True)


class LoginHistory(Model):
    class Meta:
        db_table = f"{APP_NAME}_login_histories"

        indexes = (
            Index(
                fields=(
                    "user",
                    "-logged_in_at",
                    "-logged_out_at",
                )
            ),
            Index(
                fields=(
                    "-logged_in_at",
                    "-logged_out_at",
                )
            ),
            Index(fields=("session_key",)),
        )

    user = ForeignKey(User, PROTECT)
    ip_address = GenericIPAddressField(null=True)
    # NOTE allow null because it is possible in valid situations
    #      see <https://stackoverflow.com/questions/39622922/request-session-session-key-not-set-despite-session-save-every-request-django-1>   pylint: disable=line-too-long
    # NOTE 32bytes should be enough for now
    session_key = CharField(max_length=256, null=True)
    logged_in_at = DateTimeField(auto_now_add=True)
    logged_out_at = DateTimeField(null=True)
