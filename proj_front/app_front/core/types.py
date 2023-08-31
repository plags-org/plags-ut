import datetime
import re
from typing import Any, Final, FrozenSet, Literal, Optional

import dateutil.parser
from pydantic import ConstrainedStr
from typing_extensions import TypeAlias

from app_front.core.common.regex_helper import to_compiled_fullmatch_regex
from app_front.core.google_drive.utils import get_resource_id_from_url

DjangoRequestArg: TypeAlias = Any
DjangoRequestKwarg: TypeAlias = Any

String64: TypeAlias = str
StringUrl64: TypeAlias = str
DateTimeString: TypeAlias = str

# pylint: disable=invalid-name
PATTERN_StringUrl64 = r"[a-zA-Z0-9_-]{1,64}"
REGEX_StringUrl64 = re.compile(PATTERN_StringUrl64)


def assert_Optional_Bool(some: Any) -> None:
    if some is None:
        return
    assert isinstance(some, bool)


def assert_String64(some: Any) -> None:
    assert isinstance(some, str)
    assert len(some) <= 64


def assert_StringUrl64(some: Any) -> None:
    assert REGEX_StringUrl64.fullmatch(some), f"{some!r} is not StringUrl64"


def assert_DateTimeString(some: Any) -> None:
    assert isinstance(some, str)
    dateutil.parser.isoparse(some)


def assert_Optional_DateTimeString(some: Any) -> None:
    if some is None:
        return
    assert_DateTimeString(some)


def assert_DateTimeString_convert(some: Any) -> datetime.datetime:
    assert isinstance(some, str)
    return dateutil.parser.isoparse(some)


def assert_Optional_DateTimeString_convert(some: Any) -> Optional[datetime.datetime]:
    if some is None:
        return None
    return assert_DateTimeString_convert(some)


ColaboratoryResourceID: TypeAlias = str


def assert_ColaboratoryResourceID_convert(some: Any) -> ColaboratoryResourceID:
    assert isinstance(some, str), f"invalid resource id type: {some!r}"
    maybe_resource_id = get_resource_id_from_url(some)
    assert maybe_resource_id is not None, f"invalid resource id: {some!r}"
    return maybe_resource_id


def assert_Optional_ColaboratoryResourceID_convert(
    some: Any,
) -> Optional[ColaboratoryResourceID]:
    if some is None:
        return None
    return assert_ColaboratoryResourceID_convert(some)


IsSuccess: TypeAlias = bool
Success: Final = True
Failure: Final = False

ColorRGBHex: TypeAlias = str

PATTERN_ColorRGBHex = r"#[0-9A-Fa-f]{6}"
REGEX_ColorRGBHex = re.compile(PATTERN_ColorRGBHex)


PATTERN_TagCode = r"[0-9A-Za-z]{1,16}"
REGEX_TagCode = re.compile(PATTERN_TagCode)


def assert_ColorRGBHex(some: Any) -> None:
    assert isinstance(some, str)
    assert REGEX_ColorRGBHex.fullmatch(some) is not None, f"{some!r} is not ColorRGBHex"


Activeness: TypeAlias = int

UserName: TypeAlias = str

OrganizationName: TypeAlias = str
CourseName: TypeAlias = str
ExerciseName: TypeAlias = str

ErrorMessage: TypeAlias = str
WarningMessage: TypeAlias = str
InfoMessage: TypeAlias = str


EditorName: TypeAlias = str
SUPPORTED_EDITOR_NAMES: Final[FrozenSet[EditorName]] = frozenset(("CodeMirror",))

Score: TypeAlias = int


class GoogleClientId(ConstrainedStr):
    regex = to_compiled_fullmatch_regex(
        r"[0-9]{12}-[0-9a-z]{32}\.apps\.googleusercontent\.com"
    )


GoogleOauthAccessType: TypeAlias = Literal["online", "offline"]


class MailHostName(ConstrainedStr):
    regex = to_compiled_fullmatch_regex(r"([a-z\-]+)(\.[a-z\-]+)*")


RelativeFilePath: TypeAlias = str
