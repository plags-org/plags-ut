import enum
import re
from typing import Any, List, Literal, Tuple, Type, Union

from django.core.validators import EmailValidator, RegexValidator, _lazy_re_compile
from django.db.models import CharField, IntegerField
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _
from typing_extensions import TypeAlias

from app_front.core.const import UTOKYO_ECCS_MAIL_DOMAIN
from app_front.core.types import (
    PATTERN_ColorRGBHex,
    PATTERN_StringUrl64,
    PATTERN_TagCode,
)


@deconstructible
class UsernameValidator(RegexValidator):
    regex = r"^[\w]{4,32}$"
    message = _(
        "Enter a valid username. This value may contain only letters, "
        "numbers, and _(underscores) characters, and with 4 to 32 characters."
    )
    flags = re.ASCII


@deconstructible
class StudentCardNumberValidator(RegexValidator):
    regex = r"^([\w]{2}\-[\w]{6})?$"
    message = _(
        "Enter a valid student card number. "
        "2+6 characters, with -(hyphen), like AB-123456. "
        "Recommended copy and paste from LMS. "
        "Student card number will be seen only by lecturers. "
        "Leave this blank if you have no student card number."
    )
    flags = re.ASCII


@deconstructible
class CommonIDNumberValidator(RegexValidator):
    regex = r"^\d{10}$"
    message = _(
        "Enter a valid common ID number (10 digits). "
        "Entered common ID number will be seen only by lecturers."
    )
    flags = re.ASCII


@deconstructible
class UTokyoEmailValidator(EmailValidator):
    message = _("Enter a valid ECCS Cloud Email address.")
    domain_regex = _lazy_re_compile(re.escape(UTOKYO_ECCS_MAIL_DOMAIN))
    domain_whitelist: List[str] = []


def _to_fullmatch_regex(regex: str) -> str:
    return r"^" + regex + r"$"


@deconstructible
class StringUrl64Validator(RegexValidator):
    regex = _to_fullmatch_regex(PATTERN_StringUrl64)
    message = _(
        f'Enter a valid StringUrl64. This value must fullmatch r"{PATTERN_StringUrl64}" .'
    )
    flags = re.ASCII


@deconstructible
class TagCodeValidator(RegexValidator):
    regex = _to_fullmatch_regex(PATTERN_TagCode)
    message = _(
        f'Enter a valid TagCode. This value must fullmatch r"{PATTERN_TagCode}" .'
    )
    flags = re.ASCII


@deconstructible
class ColorRGBHexValidator(RegexValidator):
    regex = _to_fullmatch_regex(PATTERN_ColorRGBHex)
    message = _(
        f'Enter a valid ColorRGBHex. This value must fullmatch r"{PATTERN_ColorRGBHex}" .'
    )
    flags = re.ASCII


DjangoChoiceFieldChoices: TypeAlias = List[Tuple[str, str]]


@enum.unique
class ChoosableEnum(str, enum.Enum):
    @classmethod
    def choices(cls) -> DjangoChoiceFieldChoices:
        return [(m.value, m.name.lower()) for m in cls]

    @classmethod
    def as_choices(cls, *values: "ChoosableEnum") -> DjangoChoiceFieldChoices:
        return [(m.value, m.name.lower()) for m in values if m in cls]

    @classmethod
    def contains(cls, val: str) -> bool:
        return val in [m.name for m in cls]


def ChoosableEnumField(
    cls: Type[ChoosableEnum], **kwargs: Any
) -> CharField:  # type:ignore[type-arg]
    max_length = max(len(e.value) for e in list(cls))
    return CharField(max_length=max_length, choices=cls.choices(), **kwargs)


def constant_class_to_choices(class_: Type[enum.Enum]) -> DjangoChoiceFieldChoices:
    return [
        (value, name)
        for name, value in vars(class_).items()
        if not name.startswith("_")
    ]


def ChoosableIntegerEnumField(
    class_: Type[enum.Enum], **kwargs: Any
) -> IntegerField:  # type:ignore[type-arg]
    return IntegerField(choices=constant_class_to_choices(class_), **kwargs)


def str_of_int_sort_safe(
    value: int,
    base_spec: Union[Literal["d"], Literal["x"]] = "d",
    block_size: int = 4,
    block_size_incr_by: int = 2,
) -> str:
    if value < dict(d=10, x=16)[base_spec] ** block_size:
        return base_spec + f"{value:0{block_size}{base_spec}}"
    return base_spec + str_of_int_sort_safe(
        value, base_spec, block_size + block_size_incr_by, block_size_incr_by
    )
