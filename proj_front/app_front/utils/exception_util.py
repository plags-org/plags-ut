"""
PLAGS UT における例外の抽象化
"""
import traceback
from types import TracebackType
from typing import Any, Callable, Literal, Optional, Sequence, Type, Union

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from typing_extensions import TypeAlias

from app_front.dependency.system_notification import SLACK_NOTIFIER

IssueToken: TypeAlias = str
ExceptionDetail: TypeAlias = Union[str, Exception, Sequence["ExceptionDetail"]]
UserResponsibleExceptionDetail: TypeAlias = Union[
    str, AssertionError, Sequence["UserResponsibleExceptionDetail"]
]
SystemResponsibleExceptionDetail: TypeAlias = ExceptionDetail

_HintKwargs: TypeAlias = Any

_IssuerType: TypeAlias = Callable[
    [Type["PlagsBaseException"], ExceptionDetail], IssueToken
]
__ISSUER: Optional[_IssuerType] = None


def get_system_error_message(process_name: str) -> str:
    return f'"{process_name}" failed due to an internal system error.'


def get_exception_message(exc: Exception) -> str:
    return f"{exc.__class__.__name__}: {str(exc)}"


def get_basic_message(issue: str, process_name: str, request: HttpRequest) -> str:
    return (
        f"Issue: {issue}\n"
        + f"On: {process_name}\n"
        + f"By: {request.user.username} ({request.user.id})\n"
        if request and request.user
        else "By: Anonymous"
    )


def get_hint_message(kwargs: _HintKwargs) -> str:
    return "\n".join(f"{key}\t= {value!r}" for key, value in kwargs.items())


def get_system_message(
    issue: str, process_name: str, request: HttpRequest, kwargs: _HintKwargs
) -> str:
    basic_message = get_basic_message(issue, process_name, request)
    hint_message = get_hint_message(kwargs)
    border = "=" * 64 + "\nHints:\n"
    return border.join(filter(None, (basic_message, hint_message)))


class PlagsBaseException(Exception):
    def __init__(self, detail: ExceptionDetail):
        if settings.DEBUG:
            super().__init__(detail)
        else:
            super().__init__()
        self.detail = detail
        # self.message: str = ''
        # self.issue_id: str = ''

        # if isinstance(detail, str):
        #     self.message = detail
        # elif isinstance(detail, AssertionError):
        #     self.message = str(detail)
        # elif isinstance(detail, Exception):
        #     if get_issuer() is not None:
        #         self.issue_id = get_issuer()(self.__class__, detail)
        #         self.message = (
        #             "Issue already reported to maintainer. Sorry for inconvenience."
        #             f"  (id = {self.issue_id})"
        #         )


class UserResponsibleException(PlagsBaseException):
    def __init__(
        self, detail: UserResponsibleExceptionDetail, **kwargs: _HintKwargs
    ) -> None:
        super().__init__(detail)
        self.kwargs = kwargs

    def get_user_message(self) -> str:
        if isinstance(self.detail, str):
            return self.detail
        if isinstance(self.detail, (list, tuple)):
            return str(
                [
                    detail.get_user_message()
                    if isinstance(detail, UserResponsibleException)
                    else str(detail)
                    for detail in self.detail
                ]
            )
        if isinstance(self.detail, AssertionError):
            return str(self.detail)

        raise SystemResponsibleException(self.detail, type_=type(self.detail))

    def get_system_message(self, process_name: str, request: HttpRequest) -> str:
        return get_system_message(
            self.get_user_message(), process_name, request, self.kwargs
        )


class SystemResponsibleException(PlagsBaseException):
    def __init__(
        self, detail: SystemResponsibleExceptionDetail, **kwargs: _HintKwargs
    ) -> None:
        super().__init__(detail)
        self.kwargs = kwargs

    def get_user_message(self, process_name: str) -> str:
        return get_system_error_message(process_name)

    def get_system_message(self, process_name: str, request: HttpRequest) -> str:
        return get_system_message(
            get_exception_message(self), process_name, request, self.kwargs
        )


class SystemLogicalError(SystemResponsibleException):
    """実装不備である場合にのみ送出すべき例外"""


class SystemResourceError(SystemResponsibleException):
    """外部資源の動作不良が疑われる場合にのみ送出すべき例外"""


class ExceptionHandler:
    def __init__(self, process_name: str, request: HttpRequest):
        self.process_name = process_name
        self.request = request

    def __message(self, messanger: Callable, message: str) -> None:
        if self.request:
            messanger(self.request, message)

    def __enter__(self) -> "ExceptionHandler":
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        _traceback: TracebackType,
    ) -> Optional[Literal[True]]:
        if exc_type is None:
            return None

        traceback.print_exc()
        # NOTE ただしこのときシステムとネットワーク切断していたりすると見れないが、それはISSUERを切り分けろというお話だな
        if isinstance(exc_value, UserResponsibleException):
            self.__message(messages.error, exc_value.get_user_message())
            SLACK_NOTIFIER.warning(
                exc_value.get_system_message(self.process_name, self.request),
                traceback.format_exc(),
            )
        elif isinstance(exc_value, SystemResponsibleException):
            self.__message(
                messages.error, exc_value.get_user_message(self.process_name)
            )
            SLACK_NOTIFIER.error(
                exc_value.get_system_message(self.process_name, self.request),
                traceback.format_exc(),
            )
        else:
            self.__message(messages.error, get_system_error_message(self.process_name))
            SLACK_NOTIFIER.critical(
                f'ExceptionHandler: process "{self.process_name}" failed unexpectedly',
                traceback.format_exc(),
            )
        return True


def set_issuer(issuer: _IssuerType) -> None:
    global __ISSUER  # pylint: disable=global-statement
    __ISSUER = issuer


def get_issuer() -> Optional[_IssuerType]:
    return __ISSUER
