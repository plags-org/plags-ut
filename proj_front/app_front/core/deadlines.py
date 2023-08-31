import abc
import datetime
from typing import (
    TYPE_CHECKING,
    Callable,
    List,
    Literal,
    Optional,
    Protocol,
    Tuple,
    Union,
)

from typing_extensions import TypeAlias

from app_front.utils.time_util import get_current_datetime

if TYPE_CHECKING:
    from app_front.utils.auth_util import UserAuthorityDict


OptionalDatetime: TypeAlias = Optional[datetime.datetime]
LazyDatetime: TypeAlias = Callable[[], datetime.datetime]
MaybeLazyDatetime: TypeAlias = Union[datetime.datetime, LazyDatetime]
LazyOptionalDatetime: TypeAlias = Callable[[], OptionalDatetime]
MaybeLazyOptionalDatetime: TypeAlias = Union[OptionalDatetime, LazyOptionalDatetime]
DeadlineOrigin: TypeAlias = Union[
    Literal[
        "default",
        "override",
        "undefined",
        "superseded by Begin",  # Exercise.opens_at only
        "superseded by End",  # Exercise.closes_at only
    ],
    str,  # e.g. f"exercise:{name}" # Course.* only
]


def _evaluate_if_lazy(maybe_lazy_datetime: MaybeLazyDatetime) -> datetime.datetime:
    if callable(maybe_lazy_datetime):
        return maybe_lazy_datetime()
    return maybe_lazy_datetime


def _evaluate_if_lazy_optional(
    maybe_lazy_datetime: MaybeLazyOptionalDatetime,
) -> Optional[datetime.datetime]:
    if callable(maybe_lazy_datetime):
        return maybe_lazy_datetime()
    return maybe_lazy_datetime


def specified_or_default(
    specified: OptionalDatetime, lazy_default: MaybeLazyDatetime
) -> Tuple[datetime.datetime, DeadlineOrigin]:
    if specified:
        return (specified, "override")
    return (_evaluate_if_lazy(lazy_default), "default")


def calculate_begins_at_with_origin(
    exercise_begins_at: OptionalDatetime, lazy_default_begins_at: MaybeLazyDatetime
) -> Tuple[datetime.datetime, DeadlineOrigin]:
    return specified_or_default(exercise_begins_at, lazy_default_begins_at)


def calculate_opens_at_with_origin(
    exercise_opens_at: OptionalDatetime, lazy_default_opens_at: MaybeLazyDatetime
) -> Tuple[datetime.datetime, DeadlineOrigin]:
    return specified_or_default(exercise_opens_at, lazy_default_opens_at)


def calculate_checks_at_with_origin(
    exercise_checks_at: OptionalDatetime,
    lazy_default_checks_at: MaybeLazyOptionalDatetime,
) -> Tuple[Optional[datetime.datetime], DeadlineOrigin]:
    if exercise_checks_at:
        return (exercise_checks_at, "override")
    if default_checks_at := _evaluate_if_lazy_optional(lazy_default_checks_at):
        return (default_checks_at, "default")
    return (None, "undefined")


def calculate_closes_at_with_origin(
    exercise_closes_at: OptionalDatetime, lazy_default_closes_at: MaybeLazyDatetime
) -> Tuple[datetime.datetime, DeadlineOrigin]:
    return specified_or_default(exercise_closes_at, lazy_default_closes_at)


def calculate_ends_at_with_origin(
    exercise_ends_at: OptionalDatetime, lazy_default_ends_at: MaybeLazyDatetime
) -> Tuple[datetime.datetime, DeadlineOrigin]:
    return specified_or_default(exercise_ends_at, lazy_default_ends_at)


class DeadlineProtocol(Protocol):
    @abc.abstractmethod
    def calculated_begins_at(self) -> datetime.datetime:
        raise NotImplementedError

    @abc.abstractmethod
    def calculated_opens_at(self) -> datetime.datetime:
        raise NotImplementedError

    @abc.abstractmethod
    def calculated_checks_at(self) -> Optional[datetime.datetime]:
        raise NotImplementedError

    @abc.abstractmethod
    def calculated_closes_at(self) -> datetime.datetime:
        raise NotImplementedError

    @abc.abstractmethod
    def calculated_ends_at(self) -> datetime.datetime:
        raise NotImplementedError


def get_deadline_status(
    deadline: DeadlineProtocol, user_authority: "UserAuthorityDict"
) -> List[Tuple[str, Optional[datetime.datetime]]]:
    """
    course/top の deadline status 欄に表示する期限の決定
    CONFIDENTIAL see <https://github.com/plags-org/plags_ut_dev/issues/58#issuecomment-766349352>
    CONFIDENTIAL
    CONFIDENTIAL 教員には別の規則が適用される
    CONFIDENTIAL see <https://github.com/plags-org/plags_ut_dev/issues/58#issuecomment-769037834>
    """
    begins_at = deadline.calculated_begins_at()
    opens_at = deadline.calculated_opens_at()
    checks_at = deadline.calculated_checks_at()
    closes_at = deadline.calculated_closes_at()
    ends_at = deadline.calculated_ends_at()

    is_check_effective = checks_at and checks_at < closes_at
    can_view_exercise = user_authority["can_view_exercise"]
    can_view_exercise_until_end = user_authority["can_view_exercise_until_end"]

    now = get_current_datetime()
    show_begins_at = now < begins_at and (
        can_view_exercise or can_view_exercise_until_end
    )
    show_opens_at = begins_at <= now < opens_at
    show_checks_at = is_check_effective and opens_at <= now < checks_at
    show_closes_at = opens_at <= now < closes_at
    show_ends_at = closes_at <= now < ends_at
    show_disabled_at = ends_at <= now and (can_view_exercise)

    show_begins_at_prime = not show_disabled_at and show_begins_at
    show_opens_at_prime = not show_disabled_at and not show_ends_at and show_opens_at
    show_checks_at_prime = show_checks_at
    show_closes_at_prime = not show_checks_at and show_closes_at
    show_ends_at_prime = show_ends_at
    show_disabled_at_prime = show_disabled_at

    if show_begins_at_prime and show_ends_at_prime:
        if begins_at < ends_at:
            show_ends_at_prime = False
        else:
            show_begins_at_prime = False

    status: List[Tuple[str, Optional[datetime.datetime]]] = []
    if show_begins_at_prime:
        status.append(("Begin", begins_at))
    if show_opens_at_prime:
        status.append(("Open", opens_at))
    if show_checks_at_prime:
        status.append(("Check", checks_at))
    if show_closes_at_prime:
        status.append(("Close", closes_at))
    if show_ends_at_prime:
        status.append(("End", ends_at))
    if show_disabled_at_prime:
        status.append(("Disabled", None))
    return status
