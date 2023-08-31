import copy
import enum
from typing import (
    Any,
    ClassVar,
    Dict,
    Final,
    Literal,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
)

from django.contrib.auth import password_validation
from django.db.models import TextChoices
from django.forms import (
    BooleanField,
    CharField,
    ChoiceField,
    DateTimeField,
    EmailField,
    FileField,
    Form,
    HiddenInput,
    IntegerField,
    MultipleChoiceField,
    NumberInput,
    PasswordInput,
    RadioSelect,
    Textarea,
    URLField,
    ValidationError,
    Widget,
)
from django.forms.utils import ErrorList
from django.forms.widgets import TextInput
from django.template.defaultfilters import filesizeformat, linebreaks_filter
from django.utils.safestring import SafeString
from django.utils.translation import gettext_lazy as _
from typing_extensions import Self

from app_front.core.common.password_strength import validate_password
from app_front.core.const import UTOKYO_ECCS_MAIL_DOMAIN
from app_front.core.custom_evaluation_tag import CustomEvaluationTagManager
from app_front.core.form_types import ExerciseConcreteIdentity
from app_front.core.plags_utils.structured_form import (
    ItemGroupPlaceholderField,
    LargeTextField,
    StructuredForm,
)
from app_front.core.submission import ReviewSubmissionAuthorityParams
from app_front.core.transitory_user import get_transitory_user_for_email
from app_front.models import (
    Course,
    Organization,
    Submission,
    TransitoryUser,
    User,
    UserAuthorityEnum,
)
from app_front.utils.models_util import (
    ColorRGBHexValidator,
    CommonIDNumberValidator,
    StringUrl64Validator,
    StudentCardNumberValidator,
    TagCodeValidator,
    UsernameValidator,
)
from app_front.utils.time_util import get_current_datetime

FieldName = str
FormChoiceType = Tuple[str, str]
FormChoicesType = Tuple[FormChoiceType, ...]


class CustomRadioSelect(RadioSelect):
    template_name = "widgets/custom_radio_select.html"


class PassphraseAuthorizationForm(Form):
    passphrase = CharField(label=_("passphrase"))

    def __init__(
        self,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        auto_id: Optional[Union[bool, str]] = "id_%s",
        prefix: Optional[str] = None,
        initial: Optional[Mapping[str, Any]] = None,
        error_class: Type[ErrorList] = ErrorList,
        label_suffix: Optional[str] = None,
        empty_permitted: bool = False,
        field_order: Optional[Sequence[FieldName]] = None,
        use_required_attribute: Optional[bool] = None,
        renderer: Any = None,
    ) -> None:
        super().__init__(
            data=data,
            files=files,
            auto_id=auto_id,
            prefix=prefix,
            initial=initial,
            error_class=error_class,
            label_suffix=label_suffix,
            empty_permitted=empty_permitted,
            field_order=field_order,
            use_required_attribute=use_required_attribute,
            renderer=renderer,
        )
        self.__passphrase: str = "(default_passphrase)"

    def set_passphrase(self, passphrase: str) -> None:
        self.__passphrase = passphrase

    def clean(self) -> Dict[str, Any]:
        if self.cleaned_data["passphrase"] != self.__passphrase:
            raise ValidationError(_("Passphrase did not match."))
        return super().clean()


class StudentCardNumberFormPart(Form):
    student_card_number_validator = StudentCardNumberValidator()
    student_card_number = CharField(
        label=_("student card number（学生証番号）"),
        min_length=9,
        max_length=9,
        help_text=_(
            "2+6 characters with hyphen (-) such as AB-123456. "
            "Recommended to copy and paste from ITC-LMS."
        ),
        validators=[student_card_number_validator],
        required=False,
    )
    # 学生証番号を持たないユーザー（教員や、番号配布前の学生）であるか
    # `student_card_number` 列の入力は意味を持たなくなる（空欄と扱う）
    no_student_card_number = BooleanField(
        label="",
        help_text=_("No student card number（特殊な事情により学生証番号を持たない）"),
        required=False,
    )

    def __init__(
        self,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        auto_id: Optional[Union[bool, str]] = "id_%s",
        prefix: Optional[str] = None,
        initial: Optional[Dict[str, Any]] = None,
        error_class: Type[ErrorList] = ErrorList,
        label_suffix: Optional[str] = None,
        empty_permitted: bool = False,
        field_order: Optional[Sequence[FieldName]] = None,
        use_required_attribute: Optional[bool] = None,
        renderer: Any = None,
    ) -> None:
        override_initial: Optional[Dict[str, Any]] = None
        if initial is not None:
            override_initial = copy.copy(initial)
            if "student_card_number" in override_initial:
                initial_student_card_number = override_initial["student_card_number"]
                override_initial[
                    "no_student_card_number"
                ] = not initial_student_card_number

        super().__init__(
            data=data,
            files=files,
            auto_id=auto_id,
            prefix=prefix,
            initial=override_initial,
            error_class=error_class,
            label_suffix=label_suffix,
            empty_permitted=empty_permitted,
            field_order=field_order,
            use_required_attribute=use_required_attribute,
            renderer=renderer,
        )

    def clean(self) -> Dict[str, Any]:
        input_count = sum(
            map(
                bool,
                (
                    self.cleaned_data.get("student_card_number"),
                    self.cleaned_data.get("no_student_card_number"),
                ),
            )
        )
        if input_count == 2:
            raise ValidationError(
                _("Invalid input: Make sure you have student card number or not.")
            )
        if input_count == 0:
            raise ValidationError(_("Student card number is required."))
        assert input_count == 1
        return super().clean()  # 有効


class ActivationPinExpirePeriodEnum(TextChoices):
    SEVEN_DAYS = ("7d", "7 days")
    THIRTY_DAYS = ("30d", "30 days")
    NINETY_DAYS = ("90d", "90 days")


class _BaseBaseUserAuthorityEnumMixin:
    @classmethod
    # ATTENTION アノテーションは UserAuthorityEnum になっているが、DB保持値は str なのでこれも str である
    def from_db_value(cls, value: Optional[UserAuthorityEnum]) -> Self:
        assert issubclass(cls, enum.Enum), cls
        # NOTE mypy が対応していないせい (enum.Enum を継承しているので定義はある)
        for choice in cls:
            if choice.value == value:
                return choice
        raise ValueError(f"{value!r} is not a valid {cls.__name__} value")

    @classmethod
    def _to_choices(cls) -> FormChoicesType:
        # ATTENTION Exercise.calculated_{field}_display_value との実装一貫性を保つこと
        # (選択肢内部値, 選択肢表示値)
        return tuple(
            (choice.value, choice.name.lower())
            for choice in cls
            if choice.value is not None
        )

    @classmethod
    def _from_choice(cls, chosen_value: str) -> Self:
        for choice in cls:
            if choice.value == chosen_value:
                return choice
        raise ValueError(f"{chosen_value!r} is not a valid {cls.__name__}")

    @classmethod
    def assert_declaration_validity(cls) -> None:
        assert issubclass(cls, enum.Enum)


class _BaseUserAuthorityEnumMixin(_BaseBaseUserAuthorityEnumMixin):
    """
    列挙型の宣言補助用 Mixin
    """

    @classmethod
    def to_choices(cls) -> FormChoicesType:
        return cls._to_choices()

    @classmethod
    def from_choice(cls, chosen_value: str) -> Self:
        return super()._from_choice(chosen_value)


class InvitedCourseAuthorityEnum(_BaseUserAuthorityEnumMixin, enum.Enum):
    # 名前 = DB保存値
    LECTURER = UserAuthorityEnum.LECTURER.value
    MANAGER = UserAuthorityEnum.MANAGER.value


InvitedCourseAuthorityEnum.assert_declaration_validity()


class CreateUserForm(StructuredForm):
    THIS_ORGANIZATION_KEY: Final[str] = "(this organization)"

    full_name = CharField(
        label=_("full name（氏名）"),
        max_length=128,
        help_text=_("Full name registered and displayed in ITC-LMS if student's."),
    )
    email = EmailField(
        label=_("email address"),
        help_text=_("Necessary to be a valid one."),
    )
    activation_pin_expire_period = ChoiceField(
        label="Expiry of activation PIN",
        choices=ActivationPinExpirePeriodEnum.choices,
        initial=ActivationPinExpirePeriodEnum.THIRTY_DAYS,
    )
    invited_to = ChoiceField(label=_("Invited to"))
    invited_to_authority = ChoiceField(
        label=_("Authority for inviting organization/course"),
        widget=CustomRadioSelect,
        choices=InvitedCourseAuthorityEnum.to_choices(),
    )

    def __init__(
        self,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        auto_id: Optional[Union[bool, str]] = "id_%s",
        prefix: Optional[str] = None,
        initial: Optional[Dict[str, Any]] = None,
        error_class: Type[ErrorList] = ErrorList,
        label_suffix: Optional[str] = None,
        empty_permitted: bool = False,
        field_order: Optional[Sequence[FieldName]] = None,
        use_required_attribute: Optional[bool] = None,
        renderer: Any = None,
        *,
        invited_course_choices: Optional[FormChoicesType],
    ) -> None:
        super().__init__(
            data=data,
            files=files,
            auto_id=auto_id,
            prefix=prefix,
            initial=initial,
            error_class=error_class,
            label_suffix=label_suffix,
            empty_permitted=empty_permitted,
            field_order=field_order,
            use_required_attribute=use_required_attribute,
            renderer=renderer,
        )

        if invited_course_choices is None:
            self.fields["invited_to"].widget = HiddenInput()
            self.fields["invited_to"].required = False
            self.fields["invited_to_authority"].widget = HiddenInput()
            self.fields["invited_to_authority"].required = False
        else:
            self.fields["invited_to"].choices = (
                (self.THIS_ORGANIZATION_KEY, self.THIS_ORGANIZATION_KEY),
            ) + invited_course_choices

    def clean(self) -> Dict[str, Any]:
        result = super().clean()
        if "invited_to" in result and "invited_to_authority" in result:
            if (
                result["invited_to"] == self.THIS_ORGANIZATION_KEY
                and result["invited_to_authority"] != UserAuthorityEnum.MANAGER.value
            ):
                raise ValidationError(
                    dict(
                        invited_to_authority=_(
                            'Authority must be "manager" when inviting to this organization.'
                        )
                    )
                )
        return result


class CreateUserByRegistrationForm(StudentCardNumberFormPart):
    full_name = CharField(
        label=_("full name（氏名）"),
        max_length=128,
        help_text=_("Your full name registered and displayed in ITC-LMS."),
    )

    # ATTENTION 意味的には email に変換されて利用されるため、フィールド名が email になっている
    email_validator = CommonIDNumberValidator()
    email = CharField(
        label=_("Common ID number（共通ID）"),
        help_text=_("The 10-digit number used as your UTokyo Account login name."),
        validators=[email_validator],
    )

    def __init__(
        self,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        auto_id: Optional[Union[bool, str]] = "id_%s",
        prefix: Optional[str] = None,
        initial: Optional[Mapping[str, Any]] = None,
        error_class: Type[ErrorList] = ErrorList,
        label_suffix: Optional[str] = None,
        empty_permitted: bool = False,
        field_order: Optional[Sequence[FieldName]] = None,
        use_required_attribute: Optional[bool] = None,
        renderer: Any = None,
    ) -> None:
        field_order = (
            "full_name",
            "email",
            "student_card_number",  # NOTE inherit
            "no_student_card_number",  # NOTE inherit
        )
        super().__init__(
            data=data,
            files=files,
            auto_id=auto_id,
            prefix=prefix,
            initial=initial,
            error_class=error_class,
            label_suffix=label_suffix,
            empty_permitted=empty_permitted,
            field_order=field_order,
            use_required_attribute=use_required_attribute,
            renderer=renderer,
        )


class RegisterActivateForm(Form):
    email = EmailField(
        label=_("Email address"),
        help_text=_("Your email address via which you received an activation PIN."),
    )
    activation_pin = CharField(
        label=_("Activation PIN"),
        max_length=64,
        help_text=_(
            "A string like <code>048c_159d_26ae_37bf_048c</code>, sent to email address above."
        ),
    )

    username_validator = UsernameValidator()
    username = CharField(
        label=_("Username"),
        min_length=4,
        max_length=32,
        help_text=_(
            "4 to 32 characters limited to letters (a-zA-Z), digits (0-9), and underscores (_)."
        ),
        validators=[username_validator],
    )

    error_messages = {
        "password_mismatch": _("The two password fields didn't match."),
    }
    password1 = CharField(
        label=_("Password"),
        strip=False,
        widget=PasswordInput,
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = CharField(
        label=_("Password confirmation"),
        widget=PasswordInput,
        strip=False,
        help_text=_("Enter the same password as before, for verification."),
    )

    def __init__(
        self,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        auto_id: Optional[Union[bool, str]] = "id_%s",
        prefix: Optional[str] = None,
        initial: Optional[Mapping[str, Any]] = None,
        error_class: Type[ErrorList] = ErrorList,
        label_suffix: Optional[str] = None,
        empty_permitted: bool = False,
        field_order: Optional[Sequence[FieldName]] = None,
        use_required_attribute: Optional[bool] = None,
        renderer: Any = None,
    ) -> None:
        super().__init__(
            data=data,
            files=files,
            auto_id=auto_id,
            prefix=prefix,
            initial=initial,
            error_class=error_class,
            label_suffix=label_suffix,
            empty_permitted=empty_permitted,
            field_order=field_order,
            use_required_attribute=use_required_attribute,
            renderer=renderer,
        )
        self.fields["email"].widget.attrs.update({"autofocus": True})

    def _post_clean(self) -> None:
        super()._post_clean()
        # Validate the password after self.instance is updated with form data
        # by super().
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, User)
            except ValidationError as error:
                self.add_error("password2", error)

    def clean_password2(self) -> str:
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError(
                self.error_messages["password_mismatch"],
                code="password_mismatch",
            )
        return password2

    def clean(self) -> Dict[str, Any]:
        # フィールド単位のバリデーションで失敗しているのでフィールドを跨いだバリデーションは実行不能、スキップ
        if "email" not in self.cleaned_data:
            return super().clean()
        if "activation_pin" not in self.cleaned_data:
            return super().clean()

        # フィールドを跨いだバリデーションを実行
        email = self.cleaned_data["email"]
        activation_pin = self.cleaned_data["activation_pin"]

        # 有効期限の切れていない、emailが一致するもののうち有効期限が最も遅いものを採用する
        transitory_user: Optional[TransitoryUser] = get_transitory_user_for_email(email)
        if transitory_user is None:
            raise ValidationError(_("Incorrect (email, activation_pin) pair."))
        if transitory_user.expired_at < get_current_datetime():
            raise ValidationError(
                _("The activation PIN for this user already expired.")
            )
        if transitory_user.activated_at is not None:
            # NOTE Userレコードが存在するかを確認したほうが良いかもしれない
            raise ValidationError(_("This user is already activated."))
        if transitory_user.activation_pin != activation_pin:
            raise ValidationError(_("Incorrect (email, activation_pin) pair."))

        # early return if data not set (already a field error)
        if (username := self.cleaned_data.get("username")) is None:
            return super().clean()
        if (password := self.cleaned_data.get("password1")) is None:
            return super().clean()
        student_card_number = transitory_user.student_card_number

        validate_password(
            email, password, activation_pin, username, student_card_number
        )
        return super().clean()


class UserResetPasswordFormForm(Form):
    email = EmailField(
        label=_("Email address"),
    )


class UserResetPasswordConfirmForm(Form):
    email = EmailField(
        label=_("Email address"),
    )
    password_reset_pin = CharField(
        label=_("Password reset PIN"),
        max_length=64,
        help_text=_(
            "A string like <code>048c_159d_26ae_37bf_048c</code>, sent to email address above."
        ),
    )

    error_messages = {
        "password_mismatch": _("The two password fields didn't match."),
    }
    password1 = CharField(
        label=_("New password"),
        strip=False,
        widget=PasswordInput,
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = CharField(
        label=_("Password confirmation"),
        widget=PasswordInput,
        strip=False,
        help_text=_("Enter the same password as before, for verification."),
    )

    def _post_clean(self) -> None:
        super()._post_clean()
        # Validate the password after self.instance is updated with form data
        # by super().
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, User)
            except ValidationError as error:
                self.add_error("password2", error)

    def clean_password2(self) -> str:
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError(
                self.error_messages["password_mismatch"],
                code="password_mismatch",
            )
        return password2

    def clean(self) -> Dict[str, Any]:
        email = self.cleaned_data["email"]
        password_reset_pin = self.cleaned_data["password_reset_pin"]

        # 有効期限の切れていない、emailが一致するもののうち有効期限が最も遅いものを採用する
        user: User = User.objects.filter(email=email).first()
        if user is None:
            # NOTE emailに該当するユーザーが存在するかどうかの情報を与えないため
            raise ValidationError(_("Incorrect (email, password_reset_pin) pair."))
        if user.password_reset_pin != password_reset_pin:
            raise ValidationError(_("Incorrect (email, password_reset_pin) pair."))

        password = self.cleaned_data["password1"]
        username = user.username
        student_card_number = user.student_card_number
        validate_password(
            email, password, password_reset_pin, username, student_card_number
        )

        return super().clean()


class RequestEmailUpdateForm(Form):
    email = EmailField()


class RequestLecturerEmailUpdateForm(RequestEmailUpdateForm):
    email = EmailField(
        label=_("Email address"),
        help_text=_(
            "<strong>ATTENTION: When updating your email address, email will be sent to a new email address. "
            "Follow instructions described in the mail. "
            "</strong>"
        ),
    )


class RequestUTokyoStudentEmailUpdateForm(RequestEmailUpdateForm):
    # ATTENTION RequestLecturerEmailUpdateForm との互換のため、フィールド名が email になっている
    email_validator = CommonIDNumberValidator()
    email = CharField(
        label=_("Common ID number"),
        help_text=_(
            "The 10-digit number used as your UTokyo Account login name. "
            "<strong>ATTENTION: When updating your account ID, "
            f"email will be sent to your address ( <code>[common ID number]@{UTOKYO_ECCS_MAIL_DOMAIN}</code> ). "
            "Follow instructions described in the mail."
            "</strong>"
        ),
        validators=[email_validator],
    )


class ApplyEmailUpdateForm(Form):
    email_updating_to = EmailField(
        label=_("New account ID"),
    )
    email_update_pin = CharField(
        label=_("Email update PIN"),
        max_length=64,
        help_text="PIN to apply your email update, to ensure that requested address is yours.",
    )


class ApplyLecturerEmailUpdateForm(ApplyEmailUpdateForm):
    email_updating_to = EmailField(
        label=_("New email address"),
    )
    email_update_pin = CharField(
        label="Account update PIN",
        max_length=64,
        help_text="PIN to apply your email update, to ensure that requested address is yours.",
    )


class ApplyUTokyoStudentEmailUpdateForm(ApplyEmailUpdateForm):
    email_validator = CommonIDNumberValidator()
    email_updating_to = CharField(
        label=_("Common ID number"),
        validators=[email_validator],
    )
    email_update_pin = CharField(
        label=_("Account update PIN"),
        max_length=64,
        help_text="PIN to apply your email update, to ensure that requested address is yours.",
    )


class UpdateUserInfoForm(Form):
    """ユーザープロフィールの編集 教員ユーザーと学生ユーザーで実装が異なるので抽象化"""

    def __init__(self, original_username: str, *args, **kwargs) -> None:
        del original_username
        super().__init__(*args, **kwargs)


class UpdateFacultyUserInfoForm(UpdateUserInfoForm):
    username_validator = UsernameValidator()
    username = CharField(
        label=_("Username"),
        min_length=4,
        max_length=32,
        help_text=_(
            "4 to 32 characters limited to letters (a-zA-Z), digits (0-9), and underscores (_)."
        ),
        validators=[username_validator],
    )

    full_name = CharField(
        label=_("full name（氏名）"),
        max_length=128,
        help_text=_("Your full name registered and displayed in ITC-LMS."),
    )

    flag_cooperate_on_research_anonymously = BooleanField(
        # pylint: disable=line-too-long
        label="",
        help_text='Anonymously cooperate on research. See <a href="https://drive.google.com/file/d/1CWXhmkPDC0KzfsO7ilZB8_pA-GGg2nJM/view?usp=sharing" target="_blank" rel="external noopener noreferrer">here</a> for the details.',
        required=False,
    )

    def __init__(self, original_username: str, *args, **kwargs) -> None:
        super().__init__(original_username, *args, **kwargs)
        self.__original_username = original_username

    def clean_username(self):
        username = self.cleaned_data["username"]
        if username == self.__original_username:
            return username
        if User.objects.filter(username=username).exists():
            raise ValidationError(_("This username is already taken."))
        return username


class UpdateStudentUserInfoForm(UpdateUserInfoForm, StudentCardNumberFormPart):
    username_validator = UsernameValidator()
    username = CharField(
        label=_("Username"),
        min_length=4,
        max_length=32,
        help_text=_(
            "4 to 32 characters limited to letters (a-zA-Z), digits (0-9), and underscores (_)."
        ),
        validators=[username_validator],
    )

    full_name = CharField(
        label=_("full name（氏名）"),
        max_length=128,
        help_text=_("Your full name registered and displayed in ITC-LMS."),
    )

    flag_cooperate_on_research_anonymously = BooleanField(
        # pylint: disable=line-too-long
        label="",
        help_text='Anonymously cooperate on research. See <a href="https://drive.google.com/file/d/1CWXhmkPDC0KzfsO7ilZB8_pA-GGg2nJM/view?usp=sharing" target="_blank" rel="external noopener noreferrer">here</a> for the details.',
        required=False,
    )

    def __init__(self, original_username: str, *args, **kwargs) -> None:
        field_order = (
            "username",
            "full_name",
            "student_card_number",  # NOTE inherit
            "no_student_card_number",  # NOTE inherit
            "flag_cooperate_on_research_anonymously",
        )
        kwargs["field_order"] = field_order
        super().__init__(original_username, *args, **kwargs)
        self.__original_username = original_username

    def clean_username(self):
        username = self.cleaned_data["username"]
        if username == self.__original_username:
            return username
        if User.objects.filter(username=username).exists():
            raise ValidationError(_("This username is already taken."))
        return username


class UpdateUserInfoByManagerForm(StudentCardNumberFormPart):
    full_name = CharField(
        label=_("full name（氏名）"),
        max_length=128,
        help_text=_("Your full name registered and displayed in ITC-LMS."),
    )

    username_validator = UsernameValidator()
    username = CharField(
        label=_("Username"),
        min_length=4,
        max_length=32,
        help_text=_(
            "4 to 32 characters limited to letters (a-zA-Z), digits (0-9), and underscores (_)."
        ),
        validators=[username_validator],
    )

    def __init__(self, original_username: str, *args, **kwargs) -> None:
        kwargs["field_order"] = (
            "username",
            "full_name",
            "student_card_number",  # NOTE inherit
            "no_student_card_number",  # NOTE inherit
        )
        super().__init__(*args, **kwargs)
        self.__original_username = original_username

    def clean(self):
        username = self.cleaned_data["username"]
        if username == self.__original_username:
            return
        if User.objects.filter(username=username).exists():
            raise ValidationError(_("This username is already taken."))


class RegisterGoogleAuthUserForm(Form):
    common_id_number_validator = CommonIDNumberValidator()
    common_id_number = CharField(
        label=_("Common ID number（共通ID）"),
        min_length=10,
        max_length=10,
        help_text=_("The 10-digit number used as your UTokyo Account login name."),
        validators=[common_id_number_validator],
    )


class ConfirmCommonIdNumberForm(Form):
    verification_token = CharField(
        label=_("Verification token"),
        min_length=40,
        max_length=40,
        help_text=_(
            "A string like <code>048c159d26ae37bf048c048c159d26ae37bf048c</code>, "
            "sent to email address <code>[common ID number]@g.ecc.u-tokyo.ac.jp</code>."
        ),
    )


class GoogleAuthTransitoryNewUserInfoForm(StudentCardNumberFormPart):
    full_name = CharField(
        label=_("Full name（氏名）"),
        max_length=128,
        help_text=_("Your full name registered and displayed in ITC-LMS."),
    )

    def __init__(self, *args, **kwargs) -> None:
        kwargs["field_order"] = (
            "full_name",
            "student_card_number",  # NOTE inherit
            "no_student_card_number",  # NOTE inherit
        )
        super().__init__(*args, **kwargs)


class UpdateUserEmailForm(Form):
    user = ChoiceField()
    email = EmailField(label=_("Email address"))

    def __init__(self, users, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["user"].choices = users


class UserPasswordUpdateForm(Form):
    password = CharField(
        label=_("Current password"),
        strip=False,
        widget=PasswordInput,
    )

    error_messages = {
        "password_mismatch": _("The two password fields didn't match."),
    }
    password1 = CharField(
        label=_("New password"),
        strip=False,
        widget=PasswordInput,
        help_text=password_validation.password_validators_help_text_html(),
    )
    password2 = CharField(
        label=_("New password confirmation"),
        widget=PasswordInput,
        strip=False,
        help_text=_("Enter the same password as before, for verification."),
    )

    def __init__(
        self,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        auto_id: Optional[Union[bool, str]] = "id_%s",
        prefix: Optional[str] = None,
        initial: Optional[Mapping[str, Any]] = None,
        error_class: Type[ErrorList] = ErrorList,
        label_suffix: Optional[str] = None,
        empty_permitted: bool = False,
        field_order: Optional[Sequence[FieldName]] = None,
        use_required_attribute: Optional[bool] = None,
        renderer: Any = None,
    ) -> None:
        super().__init__(
            data=data,
            files=files,
            auto_id=auto_id,
            prefix=prefix,
            initial=initial,
            error_class=error_class,
            label_suffix=label_suffix,
            empty_permitted=empty_permitted,
            field_order=field_order,
            use_required_attribute=use_required_attribute,
            renderer=renderer,
        )
        self._user: Optional[User] = None

    def set_user(self, user: User) -> None:
        self._user = user

    def _post_clean(self):
        super()._post_clean()
        # Validate the password after self.instance is updated with form data
        # by super().
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, User)
            except ValidationError as error:
                self.add_error("password2", error)

    def clean_password(self):
        assert self._user is not None
        password = self.cleaned_data.get("password")
        if not self._user.check_password(password):
            raise ValidationError(_("Wrong password."))

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise ValidationError(
                self.error_messages["password_mismatch"],
                code="password_mismatch",
            )
        return password2

    def clean(self) -> Dict[str, Any]:
        assert self._user is not None
        email = self._user.email
        password = self.cleaned_data["password1"]
        username = self._user.username
        student_card_number = self._user.student_card_number
        validate_password(email, password, None, username, student_card_number)

        return super().clean()


class CreateOrganizationForm(Form):
    name_validator = StringUrl64Validator()
    name = CharField(
        max_length=64,
        validators=[name_validator],
    )

    def clean(self):
        name = self.cleaned_data.get("name")
        if Organization.objects.filter(name=name).count():
            raise ValidationError("Requested name already taken. Try another one.")
        return self.cleaned_data


class _BaseUserAuthorityWithDefaultEnumMixin(_BaseBaseUserAuthorityEnumMixin):
    """
    default 選択肢つきの列挙型の宣言補助用 Mixin

    Course, Exercise 両方で設定可能で、Exercise の設定をオーバーライドできるような設定項目に利用する
    """

    _DEFAULT_FORM_VALUE: Final[Literal["default"]] = "default"

    # ATTENTION 継承側で定義すべし
    DEFAULT: ClassVar[Self]

    @classmethod
    def to_course_choices(cls) -> FormChoicesType:
        # ATTENTION Exercise.calculated_{field}_display_value との実装一貫性を保つこと
        # (選択肢内部値, 選択肢表示値)
        return cls._to_choices()

    @classmethod
    def to_exercise_choices(cls, current_default: UserAuthorityEnum) -> FormChoicesType:
        # ATTENTION Exercise.calculated_{field}_display_value との実装一貫性を保つこと
        # (選択肢内部値, 選択肢表示値)
        # NOTE None は「無選択」と判定されてしまうので回避
        return cls.to_course_choices() + (
            (
                cls._DEFAULT_FORM_VALUE,
                f"Default (current: {current_default.to_display_name()})",
            ),
        )

    @classmethod
    def from_choice(cls, chosen_value: str) -> Self:
        # NOTE None は「無選択」と判定されてしまうので回避
        if chosen_value == cls._DEFAULT_FORM_VALUE:
            return cls.DEFAULT  # type:ignore[return-value]
        return super()._from_choice(chosen_value)

    @classmethod
    def assert_declaration_validity(cls) -> None:
        assert hasattr(cls, "DEFAULT"), cls
        assert isinstance(cls.DEFAULT, cls), cls
        super().assert_declaration_validity()


class ScoreVisibleFromEnum(_BaseUserAuthorityWithDefaultEnumMixin, enum.Enum):
    # NOTE Exercise 向けのときは None as default とする
    DEFAULT = None

    # 名前 = DB保存値
    STUDENT = UserAuthorityEnum.STUDENT.value
    ASSISTANT = UserAuthorityEnum.ASSISTANT.value
    LECTURER = UserAuthorityEnum.LECTURER.value

    # ATTENTION 以下の実装一貫性を保つこと:
    # - cls.to_{ce}_choices
    # - Exercise.calculated_score_visible_from_display_value


ScoreVisibleFromEnum.assert_declaration_validity()


class RemarksVisibleFromEnum(_BaseUserAuthorityWithDefaultEnumMixin, enum.Enum):
    # NOTE Exercise 向けのときは None as default とする
    DEFAULT = None

    # 名前 = DB保存値
    ASSISTANT = UserAuthorityEnum.ASSISTANT.value
    LECTURER = UserAuthorityEnum.LECTURER.value

    # ATTENTION 以下の実装一貫性を保つこと:
    # - cls.to_{ce}_choices
    # - Exercise.calculated_score_visible_from_display_value


RemarksVisibleFromEnum.assert_declaration_validity()


class CreateCourseForm(StructuredForm):
    _group_basics = ItemGroupPlaceholderField("Basic info")

    name_validator = StringUrl64Validator()
    name = CharField(
        max_length=64,
        help_text="Course identifier. StringUrl64. Used as part of URL. Must be unique in Organization.",
        validators=[name_validator],
    )

    title = CharField(
        max_length=128,
        help_text=(
            "Course title in natural language. "
            "Filled with <code>{{ organization.name }} / {{ course.name }}</code> if empty."
        ),
    )
    body = LargeTextField(
        label="Description",
        max_length=65536,
        help_text="Course description in Markdown",
        required=False,
        initial="# Course description",
    )

    is_registerable = BooleanField(
        label=_("Registerable"),
        required=False,
        help_text="Allow student registration",
    )

    _group_defaults = ItemGroupPlaceholderField("Default settings for exercises")

    exercise_default_begins_at = DateTimeField(
        label="Begin",
        help_text=_("Default begin for all the exercises"),
    )
    exercise_default_opens_at = DateTimeField(
        label="Open",
        help_text=_("Default open for all the exercises"),
    )
    exercise_default_checks_at = DateTimeField(
        label="Check",
        help_text=_("Default check for all the exercises (optional)"),
        required=False,
    )
    exercise_default_closes_at = DateTimeField(
        label="Close",
        help_text=_("Default close for all the exercises"),
    )
    exercise_default_ends_at = DateTimeField(
        label="End",
        help_text=_("Default end for all the exercises"),
    )

    exercise_default_is_shared_after_confirmed = BooleanField(
        label="Shared after confirmed",
        required=False,
        help_text=_(
            'Default "shared after confirmed" setting for all the exercises. '
            "If checked, confirmed submissions will be shared across students."
        ),
    )
    exercise_default_score_visible_from = ChoiceField(
        label="Confidentiality of score",
        initial="student",
        help_text=_(
            'Default "confidentiality of score" setting for all the exercises. '
            "Scores are visible to users who have authority >= a selected one."
        ),
        widget=CustomRadioSelect,
    )
    exercise_default_remarks_visible_from = ChoiceField(
        label="Confidentiality of remarks",
        initial="assistant",
        help_text=_(
            'Default "confidentiality of remarks" setting for all the exercises. '
            "Remarks are visible to users who have authority >= a selected one."
        ),
        widget=CustomRadioSelect,
    )

    def clean(self) -> dict:
        name = self.cleaned_data.get("name")
        if Course.objects.filter(organization=self._organization, name=name).count():
            raise ValidationError("Requested name already taken. Try another one.")
        return self.cleaned_data

    def __init__(self, organization: Organization, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._organization = organization
        self.fields[
            "exercise_default_score_visible_from"
        ].choices = ScoreVisibleFromEnum.to_course_choices()
        self.fields[
            "exercise_default_remarks_visible_from"
        ].choices = RemarksVisibleFromEnum.to_course_choices()


class EditCourseForm(StructuredForm):
    _group_basics = ItemGroupPlaceholderField("Basic info")

    # readonly field
    name = CharField(
        max_length=64,
        help_text="Course identifier. StringUrl64. Used as part of URL. Must be unique in Organization.",
        disabled=True,
        required=False,
    )

    title = CharField(max_length=128, help_text="Course title in natural language")
    # body: moved to EditCourseDescriptionForm

    is_registerable = BooleanField(
        label=_("Registerable"),
        required=False,
        help_text="Allow student registration",
    )

    _group_defaults = ItemGroupPlaceholderField("Default settings for exercises")

    exercise_default_begins_at = DateTimeField(
        label="Begin",
        help_text=_("Default begin for all the exercises"),
    )
    exercise_default_opens_at = DateTimeField(
        label="Open",
        help_text=_("Default open for all the exercises"),
    )
    exercise_default_checks_at = DateTimeField(
        label="Check",
        help_text=_("Default check for all the exercises (optional)"),
        required=False,
    )
    exercise_default_closes_at = DateTimeField(
        label="Close",
        help_text=_("Default close for all the exercises"),
    )
    exercise_default_ends_at = DateTimeField(
        label="End",
        help_text=_("Default end for all the exercises"),
    )

    exercise_default_is_shared_after_confirmed = BooleanField(
        label="Shared after confirmed",
        required=False,
        help_text=_(
            'Default "shared after confirmed" setting for all the exercises. '
            "If checked, confirmed submissions will be shared across students."
        ),
    )
    exercise_default_score_visible_from = ChoiceField(
        label="Confidentiality of score",
        help_text=_(
            'Default "confidentiality of score" setting for all the exercises. '
            "Scores are visible to users who have authority >= a selected one."
        ),
        widget=CustomRadioSelect,
    )
    exercise_default_remarks_visible_from = ChoiceField(
        label="Confidentiality of remarks",
        help_text=_(
            'Default "confidentiality of remarks" setting for all the exercises. '
            "Remarks are visible to users who have authority >= a selected one."
        ),
        widget=CustomRadioSelect,
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields[
            "exercise_default_score_visible_from"
        ].choices = ScoreVisibleFromEnum.to_course_choices()
        self.fields[
            "exercise_default_remarks_visible_from"
        ].choices = RemarksVisibleFromEnum.to_course_choices()


class DeleteCourseForm(StructuredForm):
    is_active = BooleanField(initial=False, required=False, disabled=True)


class RestoreCourseForm(StructuredForm):
    is_active = BooleanField(initial=True, required=False, disabled=True)


class EditCourseDescriptionForm(StructuredForm):
    body = LargeTextField(
        label="Description",
        max_length=65536,
        help_text="Course description in Markdown",
        required=False,
    )


class MultipleCourseChoiceFormPart(Form):
    courses = MultipleChoiceField(
        help_text="Select courses to perform action (multiple choice)"
    )

    def __init__(self, *args, **kwargs) -> None:
        course_choices: FormChoicesType = kwargs.pop("course_choices")
        super().__init__(*args, **kwargs)
        self.fields["courses"].choices = course_choices


class CreateCourseTopNoticeByOrganizationForm(
    StructuredForm, MultipleCourseChoiceFormPart
):
    title = CharField(label="Course-top notice title", max_length=250, required=False)
    text = CharField(
        label="Course-top notice text",
        max_length=4000,
        widget=Textarea(attrs={"style": "width: 100%;"}),
        required=False,
        help_text="ATTENTION: this text will be used as raw HTML (unescaped)",
    )
    is_public_to_students = BooleanField(
        label="", required=False, help_text=_("Visible to course users")
    )


class IsSharedAfterConfirmedEnum(enum.Enum):
    # 名前 = DB保存値
    YES = True
    NO = False
    DEFAULT = None

    @classmethod
    def from_db_value(cls, value: Optional[bool]) -> "IsSharedAfterConfirmedEnum":
        for choice in IsSharedAfterConfirmedEnum:
            if choice.value is value:
                return choice
        raise ValueError(f"{value!r} is not a valid {cls.__name__} value")

    @classmethod
    def to_choices(cls, current_default: bool) -> FormChoicesType:
        # NOTE Exercise.calculated_is_shared_after_confirmed_display_value との実装一貫性を保つこと
        current_default_str: str = "Yes" if current_default else "No"
        # (選択肢内部値, 選択肢表示値)
        return (
            (cls.YES.name, "Yes"),
            (cls.NO.name, "No"),
            (cls.DEFAULT.name, f"Default (current: {current_default_str})"),
        )

    @classmethod
    def from_choice(cls, chosen_name: str) -> "IsSharedAfterConfirmedEnum":
        for choice in IsSharedAfterConfirmedEnum:
            if choice.name == chosen_name:
                return choice
        raise ValueError(f"{chosen_name!r} is not a valid {cls.__name__}")


class EditExerciseForm(StructuredForm):
    title = CharField(max_length=128, help_text="Exercise title in natural language")

    begins_at = DateTimeField(
        label="Begin", help_text="Become visible to student (optional)", required=False
    )
    opens_at = DateTimeField(
        label="Open", help_text="Start accepting submissions (optional)", required=False
    )
    checks_at = DateTimeField(
        label="Check",
        help_text="Official deadline; accept as delayed after this (optional)",
        required=False,
    )
    closes_at = DateTimeField(
        label="Close",
        help_text="Close accepting submissions (optional)",
        required=False,
    )
    ends_at = DateTimeField(
        label="End",
        help_text="Become invisible to student/assistant (optional)",
        required=False,
    )

    is_shared_after_confirmed = ChoiceField(
        label="Shared after confirmed",
        help_text=_(
            '"shared after confirmed" setting for specified exercise. '
            'If "Yes", confirmed submissions will be shared across students.'
        ),
        widget=CustomRadioSelect,
    )
    score_visible_from = ChoiceField(
        label="Confidentiality of score",
        help_text=_(
            "Scores are visible to users who have authority >= a selected one."
        ),
        widget=CustomRadioSelect,
    )
    remarks_visible_from = ChoiceField(
        label="Confidentiality of remarks",
        help_text=_(
            "Remarks are visible to users who have authority >= a selected one."
        ),
        widget=CustomRadioSelect,
    )
    is_draft = BooleanField(
        label=_("Draft mode"),
        help_text=_("Make exercise invisible from students."),
        required=False,
    )

    drive = CharField(
        max_length=255,
        help_text="Google Drive resource ID for form *.ipynb file.<br>"
        "Both URL and raw ID format are accepted.",
        required=False,
    )

    def __init__(
        self,
        *,
        default_is_shared_after_confirmed: bool,
        default_score_visible_from: UserAuthorityEnum,
        default_remarks_visible_from: UserAuthorityEnum,
        data: Optional[Mapping[str, Any]] = None,
        files: Optional[Mapping[str, Any]] = None,
        auto_id: Optional[Union[bool, str]] = "id_%s",
        prefix: Optional[str] = None,
        initial: Optional[Mapping[str, Any]] = None,
        error_class: Type[ErrorList] = ErrorList,
        label_suffix: Optional[str] = None,
        empty_permitted: bool = False,
        field_order: Optional[Any] = None,
        use_required_attribute: Optional[bool] = None,
        renderer: Any = None,
    ) -> None:
        super().__init__(
            data=data,
            files=files,
            auto_id=auto_id,
            prefix=prefix,
            initial=initial,
            error_class=error_class,
            label_suffix=label_suffix,
            empty_permitted=empty_permitted,
            field_order=field_order,
            use_required_attribute=use_required_attribute,
            renderer=renderer,
        )
        self.fields[
            "is_shared_after_confirmed"
        ].choices = IsSharedAfterConfirmedEnum.to_choices(
            default_is_shared_after_confirmed
        )
        self.fields[
            "score_visible_from"
        ].choices = ScoreVisibleFromEnum.to_exercise_choices(default_score_visible_from)
        self.fields[
            "remarks_visible_from"
        ].choices = RemarksVisibleFromEnum.to_exercise_choices(
            default_remarks_visible_from
        )


class UploadCourseUserLmsExcelFile(Form):
    course_user_lms_excel_file = FileField(
        help_text="ITC-LMS上の課題欄 [全体提出状況確認] からダウンロードできるxlsx"
    )


MAX_ALLOWED_SUBMISSION_FILE_SIZE = 1 * 1024 * 1024


class SubmitSubmissionParcelForm(Form):
    submission_colaboratory_url = URLField(
        label=_("Online ipynb"),
        max_length=2047,
        required=False,
        help_text="A URL to Google Drive or Colaboratory, shared as 'Anyone with the link'."
        # widget=HiddenInput(),   # WORKAROUND Colabリンク提出失敗問題が解消するまでの措置
    )
    submission_parcel_file = FileField(
        label=_("Local ipynb"),
        required=False,
    )

    def clean(self):
        super().clean()
        max_file_size = MAX_ALLOWED_SUBMISSION_FILE_SIZE
        submission_parcel_file = self.cleaned_data["submission_parcel_file"]
        if submission_parcel_file:
            if submission_parcel_file.size > max_file_size:
                raise ValidationError(
                    _(
                        "Please keep filesize under %(max_size)s. (Current filesize is %(current_size)s.)"
                    )
                    % dict(
                        max_size=filesizeformat(max_file_size),
                        current_size=filesizeformat(submission_parcel_file.size),
                    )
                )


class UploadExerciseFormPart(Form):
    upload_file = FileField(
        label=_("Exercise configuration"),
        help_text=_(
            "conf.zip built with plags-scripts. "
            'See the repository for the details: <a href="https://github.com/plags-org/plags-scripts">https://github.com/plags-org/plags-scripts</a>'
        ),
    )


class UploadExerciseForm(UploadExerciseFormPart):
    # NOTE UploadExerciseForeachCourseForm に複製がある
    overwrite_deadlines = BooleanField(required=False, initial=False)
    as_draft = BooleanField(required=False, initial=False)


class UploadExerciseFormForm(Form):
    upload_file = FileField(
        label=_("Exercise form(s)"),
        help_text=_("A form zip or a single form notebook file."),
    )


class UploadExerciseForeachCourseForm(
    UploadExerciseFormPart, MultipleCourseChoiceFormPart
):
    # NOTE overwrite_deadlines, as_draft は UploadExerciseForm に複製がある

    overwrite_title = BooleanField(required=False, initial=False)
    overwrite_deadlines = BooleanField(required=False, initial=False)
    overwrite_drive = BooleanField(required=False, initial=False)
    overwrite_shared_after_confirmed = BooleanField(required=False, initial=False)
    overwrite_confidentiality = BooleanField(required=False, initial=False)
    as_draft = BooleanField(required=False, initial=False)
    overwrite_draft = BooleanField(
        label="Overwrite draft mode", required=False, initial=False
    )


# deprecated
class MetaOCAddUserForm(Form):
    user = ChoiceField()
    user_authority = ChoiceField(widget=CustomRadioSelect)

    def __init__(self, users, *args, user_authority_choices=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["user"].choices = users
        self.fields["user_authority"].choices = (
            user_authority_choices or UserAuthorityEnum.choices()
        )


KEY_REMOVE = "(remove)"


class MetaOCChangeUserForm(Form):
    user = ChoiceField()
    user_authority = ChoiceField(widget=CustomRadioSelect)

    def __init__(self, users, *args, user_authority_choices=None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["user"].choices = users
        self.fields["user_authority"].choices = (
            user_authority_choices or UserAuthorityEnum.choices()
        ) + [(KEY_REMOVE, KEY_REMOVE)]


class MetaOCRemoveUserForm(Form):
    user = ChoiceField()

    def __init__(self, users, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["user"].choices = users


class MetaOCDeactivateUsersForm(Form):
    usernames = CharField(
        max_length=65536,
        widget=Textarea,
        help_text=_(
            "Foreach line, `line.split(maxsplit=1)[0].strip()` is recognized as username."
        ),
    )

    def clean_usernames(self):
        usernames = self.cleaned_data["usernames"]
        clean_usernames = [
            line.split(maxsplit=1)[0].strip() for line in usernames.strip().split("\n")
        ]
        unknown_names = [
            username
            for username in clean_usernames
            if not User.objects.filter(username=username).exists()
        ]
        if unknown_names:
            raise ValidationError(
                _("Following usernames do not exist:\n%(unknown_names)s")
                % dict(unknown_names=", ".join(unknown_names))
            )
        self.cleaned_data["clean_usernames"] = clean_usernames


class MetaOCKickoutUsersForm(Form):
    usernames = CharField(
        max_length=65536,
        widget=Textarea,
        help_text=_(
            "Foreach line, `line.split(maxsplit=1)[0].strip()` is recognized as username."
        ),
    )

    def clean_usernames(self):
        usernames = self.cleaned_data["usernames"]
        clean_usernames = [
            line.split(maxsplit=1)[0].strip() for line in usernames.strip().split("\n")
        ]
        unknown_names = [
            username
            for username in clean_usernames
            if not User.objects.filter(username=username).exists()
        ]
        if unknown_names:
            raise ValidationError(
                _("Following usernames do not exist:\n%(unknown_names)s")
                % dict(unknown_names=", ".join(unknown_names))
            )
        self.cleaned_data["clean_usernames"] = clean_usernames


class SubmitFileForm(Form):
    exercise_name = ChoiceField()
    submission_file = FileField()

    def __init__(self, exercise_name_choices, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["exercise_name"].choices = exercise_name_choices

    MAX_SUBMISSION_FILE_SIZE: Final = 65535

    def clean(self):
        submission_file = self.cleaned_data["submission_file"]
        if submission_file.size > self.MAX_SUBMISSION_FILE_SIZE:
            raise ValidationError(
                _(
                    "Please keep filesize under %(max_size)s. (Current filesize is %(current_size)s.)"
                )
                % (
                    filesizeformat(self.MAX_SUBMISSION_FILE_SIZE),
                    filesizeformat(submission_file.size),
                )
            )


class SubmitEditorForm(Form):
    submission_source = CharField(max_length=65535, label="")
    exercise_name = CharField(max_length=64, widget=HiddenInput())
    exercise_version = CharField(max_length=64, widget=HiddenInput(), required=False)
    exercise_concrete_hash = CharField(max_length=64, widget=HiddenInput())

    def __init__(
        self,
        exercise_concrete_identity: Optional[ExerciseConcreteIdentity],
        editor_textarea_attrs: dict,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.fields["submission_source"].widget = Textarea(attrs=editor_textarea_attrs)
        self.fields["submission_source"].strip = False
        if exercise_concrete_identity is not None:
            self.fields["exercise_name"].initial = exercise_concrete_identity.name
            self.fields["exercise_version"].initial = exercise_concrete_identity.version
            self.fields[
                "exercise_concrete_hash"
            ].initial = exercise_concrete_identity.concrete_hash


class VisibleToAuthorityLabelMixin(Widget):
    def __init__(self, attrs: Optional[Any] = None) -> None:
        assert attrs and "visible_to" in attrs, attrs
        assert isinstance(attrs["visible_to"], str), attrs["visible_to"]
        visible_to = attrs["visible_to"]

        super().__init__(attrs)

        self._visible_to = visible_to

    def render(
        self,
        name: str,
        value: Any,
        attrs: Optional[Any] = None,
        renderer: Optional[Any] = None,
    ) -> SafeString:
        return super().render(name, value, attrs, renderer) + SafeString(
            f'<span style="margin-left: 16px">(visible to {self._visible_to})</span>'
        )


class DetailSummaryMixin(Textarea):
    def __init__(self, attrs: Optional[Any] = None) -> None:
        summary_label: str = "Click to expand"
        hidden: bool = False
        if attrs:
            if "summary_label" in attrs:
                assert isinstance(attrs["summary_label"], str), attrs["summary_label"]
                summary_label = attrs.pop("summary_label")
            if "hidden" in attrs:
                assert isinstance(attrs["hidden"], bool), attrs["hidden"]
                hidden = attrs.pop("hidden")

        super().__init__(attrs)

        self._summary_label = summary_label
        self._hidden = hidden

    def render(self, name, value, attrs=None, renderer=None):
        """Render the widget as an HTML string."""
        detail = ""
        if not self._hidden:
            detail = super().render(name, value, attrs=attrs, renderer=renderer)
        return SafeString(
            '<details style="display:inline-block; min-width:421px"><summary>'
            + self._summary_label
            + "</summary>"
            + detail
            + "</details>"
        )


class ReviewerRemarkTextarea(
    VisibleToAuthorityLabelMixin, DetailSummaryMixin, Textarea
):
    pass


class ReviewerScoreInput(VisibleToAuthorityLabelMixin, NumberInput):
    pass


class ReviewSubmissionForm(Form):
    is_confirmed = BooleanField(label=_("Confirmed"), required=False)
    reviewer_remarks = LargeTextField(
        label=_("Remarks"), max_length=4095, required=False
    )
    review_grade = IntegerField(label=_("Score"), required=False)
    review_comment = CharField(
        label=_("Comment"),
        max_length=4095,
        required=False,
        widget=Textarea(),
        help_text="Review comment in Markdown",
    )

    def __init__(
        self,
        *args: Any,
        authority_params: ReviewSubmissionAuthorityParams,
        initial_submission: Submission = None,
        dom_event_oninput: str = None,
        **kwargs: Any,
    ) -> None:
        if initial_submission is not None:
            assert "initial" not in kwargs
            initial: Dict[str, Any] = dict(
                review_comment=initial_submission.lecturer_comment,
            )
            if authority_params.is_confirmable:
                initial.update(
                    is_confirmed=initial_submission.is_lecturer_evaluation_confirmed,
                )
            if authority_params.can_view_submission_score:
                initial.update(
                    review_grade=initial_submission.lecturer_grade,
                )
            if authority_params.can_view_submission_remarks:
                initial.update(
                    reviewer_remarks=initial_submission.reviewer_remarks,
                )
            kwargs["initial"] = initial

        super().__init__(*args, **kwargs)

        if not authority_params.is_confirmable:
            self.fields["is_confirmed"].widget = HiddenInput()

        score_visible_to_str = ", ".join(
            auth.to_display_name()
            for auth in (
                UserAuthorityEnum.STUDENT,
                UserAuthorityEnum.ASSISTANT,
                UserAuthorityEnum.LECTURER,
            )
            if auth >= authority_params.score_visible_from
        )

        if authority_params.can_view_submission_score:
            self.fields["review_grade"].widget = ReviewerScoreInput(
                attrs=dict(
                    visible_to=score_visible_to_str,
                )
            )
        else:
            self.fields["review_grade"].widget = HiddenInput()

        remarks_visible_to_str = ", ".join(
            auth.to_display_name()
            for auth in (UserAuthorityEnum.ASSISTANT, UserAuthorityEnum.LECTURER)
            if auth >= authority_params.remarks_visible_from
        )

        if authority_params.can_view_submission_remarks:
            self.fields["reviewer_remarks"].widget = ReviewerRemarkTextarea(
                attrs=dict(
                    visible_to=remarks_visible_to_str,
                )
            )
        else:
            self.fields["reviewer_remarks"].widget = ReviewerRemarkTextarea(
                attrs=dict(
                    summary_label="🚫 (sealed)",
                    visible_to=remarks_visible_to_str,
                    hidden=True,
                )
            )

        # NOTE bulk_review で DOM への入力イベントを捕捉するため
        if dom_event_oninput is not None:
            for field in self.fields.values():
                field.widget.attrs["oninput"] = dom_event_oninput


class CreateCustomEvaluationTagForm(Form):
    code_validator = TagCodeValidator()
    code = CharField(
        min_length=1,
        max_length=16,
        help_text=_("1 to 16 characters limited to letters (a-zA-Z), digits (0-9)."),
        validators=[code_validator],
    )

    description = CharField(max_length=250, help_text=_("displayed on tag tooltip."))

    color_validator = ColorRGBHexValidator()
    background_color = CharField(
        widget=TextInput(attrs={"type": "color"}),
        validators=[color_validator],
    )
    color = CharField(
        label=_("Font color"),
        widget=TextInput(attrs={"type": "color"}),
        validators=[color_validator],
    )

    is_visible_to_students = BooleanField(
        label=_("Visible to students"),
        required=False,
    )

    def clean_code(self) -> str:
        code = self.cleaned_data["code"]
        if CustomEvaluationTagManager.is_builtin(code):
            raise ValidationError(f"tag code {code!r} is reserved (builtin code)")
        return code


class EditCustomEvaluationTagForm(Form):
    code = CharField(max_length=16, disabled=True, required=False)
    description = CharField(max_length=250)

    color_validator = ColorRGBHexValidator()
    background_color = CharField(
        widget=TextInput(attrs={"type": "color"}),
        validators=[color_validator],
    )
    color = CharField(
        label=_("Font color"),
        widget=TextInput(attrs={"type": "color"}),
        validators=[color_validator],
    )

    is_visible_to_students = BooleanField(
        label=_("Visible to students"),
        required=False,
    )


class AdministrationDataMigrationForm(PassphraseAuthorizationForm):
    verbose = BooleanField(required=False)


class AdministrationSystemSettingsForm(Form):
    use_login_page_notice = BooleanField(
        required=False, help_text="Display notice text on accounts/login page"
    )
    login_page_notice_title = CharField(max_length=250, required=False)
    login_page_notice_text = CharField(
        max_length=4000,
        widget=Textarea,
        required=False,
        help_text="ATTENTION: this text will be used as raw HTML (unescaped)",
    )


class AdministrationSystemEmailToAddressOverrideForm(Form):
    enabled = BooleanField(
        required=False,
        help_text='Override "To" address for all emails sent from system',
    )
    email = EmailField(
        required=False,
        help_text="If enabled, all system emails will be sent to this email address",
    )

    def clean(self) -> Dict[str, Any]:
        result = super().clean()
        if result is None:
            return result
        if any(key not in result for key in ("enabled", "email")):
            return result

        # 全て適正な入力であったので追加の検査を行う
        if result["enabled"] and not result["email"]:
            self.add_error(None, _("Fill email field to enable"))

        return result


class AdministrationSystemEmailSendTestForm(Form):
    target = EmailField(max_length=65536, help_text="Target address")
    subject = CharField(max_length=256, help_text="Mail subject", initial="Test mail")
    body_template = CharField(
        max_length=65536,
        widget=Textarea,
        help_text="Body template (raw HTML)",
        initial="<h2>HTML mail content</h2>\n"
        "<ol>\n"
        "  <li>Ordered item 0</li>\n"
        "  <li>Ordered item 1</li>\n"
        "  <li>Ordered item 2</li>\n"
        "</ol>",
    )


class AdministrationSendMailBulkForm(PassphraseAuthorizationForm):
    targets = CharField(
        max_length=65536, widget=Textarea, help_text="Target addresses / User IDs"
    )
    subject = CharField(max_length=256, help_text="Mail subject")
    body_template = CharField(
        max_length=65536, widget=Textarea, help_text="Body template (raw HTML)"
    )


def _as_markdown(markdown: Optional[str]) -> str:
    if markdown is None:
        return ""
    return f"""<div class="static_markdown_content" style="margin: 4px">{linebreaks_filter(markdown)}</div>"""
