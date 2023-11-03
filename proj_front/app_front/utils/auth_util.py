import contextlib
import dataclasses
import enum
import traceback
from functools import wraps
from typing import Callable, Final, Literal, Optional, Tuple, TypedDict, Union
from urllib.parse import urlparse

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import resolve_url
from typing_extensions import Concatenate, ParamSpec, TypeAlias

from app_front.core.api_decorator import ApiErrorData, api_error_response
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.types import DjangoRequestArg, DjangoRequestKwarg
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import (
    Course,
    CourseUser,
    Organization,
    OrganizationUser,
    User,
    UserAuthorityEnum,
)
from app_front.utils.exception_util import (
    SystemResponsibleException,
    UserResponsibleException,
)
from app_front.utils.parameter_decoder import get_course, get_organization


class AuthorityTargetEnum(enum.Enum):
    ORGANIZATION = "organization"
    COURSE = "course"


class ActionEnum(enum.Enum):
    VIEW = "view"
    EDIT = "edit"


class UserAuthorityDict(TypedDict):
    is_superuser: bool  # システム管理者ユーザーである
    is_faculty: bool  # 教員アカウントである
    is_active: bool  # 有効なアカウントである
    is_transitory: bool  # 仮アカウントである
    has_no_authority: bool
    on_organization: UserAuthorityEnum
    on_course: UserAuthorityEnum
    can_invite_user: bool  # 組織に紐付かないユーザーを招待できる
    can_invite_user_to_organization: bool  # 組織に紐付くユーザーを招待できる
    can_manage_user: bool
    can_manage_organization_user: bool
    can_manage_course_user: bool
    # can_create_organization: bool
    # can_activate_organization: bool
    can_edit_organization: bool
    can_view_organization: bool
    can_create_course: bool
    # can_activate_course: bool
    can_view_course_operation_log: bool
    can_view_async_job_history: bool
    can_view_course_published: bool
    can_view_course: bool
    can_edit_course: bool
    can_create_exercise: bool
    can_view_exercise_published: bool
    can_view_exercise_until_end: bool
    can_view_exercise: bool
    can_edit_exercise: bool
    can_confirm_submission: bool
    can_review_submission: bool
    can_list_submission: bool
    can_submit_submission: bool
    can_rejudge_submission: bool


UserAuthorityCapabilityKeyT = Literal[
    "is_superuser",
    "is_faculty",
    "is_active",
    "is_transitory",
    "has_no_authority",
    "can_invite_user",
    "can_invite_user_to_organization",
    "can_manage_user",
    "can_manage_organization_user",
    "can_manage_course_user",
    # "can_create_organization",
    # "can_activate_organization",
    "can_edit_organization",
    "can_view_organization",
    "can_create_course",
    # "can_activate_course",
    "can_view_course_published",
    "can_view_course",
    "can_edit_course",
    "can_create_exercise",
    "can_view_course_operation_log",
    "can_view_async_job_history",
    "can_view_exercise_published",
    "can_view_exercise_until_end",
    "can_view_exercise",
    "can_edit_exercise",
    "can_confirm_submission",
    "can_review_submission",
    "can_list_submission",
    "can_submit_submission",
    "can_rejudge_submission",
]


class UserAuthorityCapabilityKeys:
    IS_SUPERUSER: UserAuthorityCapabilityKeyT = "is_superuser"
    IS_FACULTY: UserAuthorityCapabilityKeyT = "is_faculty"
    IS_ACTIVE: UserAuthorityCapabilityKeyT = "is_active"
    IS_TRANSITORY: UserAuthorityCapabilityKeyT = "is_transitory"
    HAS_NO_AUTHORITY: UserAuthorityCapabilityKeyT = "has_no_authority"
    CAN_INVITE_USER: UserAuthorityCapabilityKeyT = "can_invite_user"
    CAN_INVITE_USER_TO_ORGANIZATION: UserAuthorityCapabilityKeyT = (
        "can_invite_user_to_organization"
    )
    CAN_MANAGE_USER: UserAuthorityCapabilityKeyT = "can_manage_user"
    CAN_MANAGE_ORGANIZATION_USER: UserAuthorityCapabilityKeyT = (
        "can_manage_organization_user"
    )
    CAN_MANAGE_COURSE_USER: UserAuthorityCapabilityKeyT = "can_manage_course_user"
    # CAN_CREATE_ORGANIZATION: UserAuthorityCapabilityKeyT = "can_create_organization"
    # CAN_ACTIVATE_ORGANIZATION: UserAuthorityCapabilityKeyT = "can_activate_organization"
    CAN_EDIT_ORGANIZATION: UserAuthorityCapabilityKeyT = "can_edit_organization"
    CAN_VIEW_ORGANIZATION: UserAuthorityCapabilityKeyT = "can_view_organization"
    CAN_CREATE_COURSE: UserAuthorityCapabilityKeyT = "can_create_course"
    # CAN_ACTIVATE_COURSE: UserAuthorityCapabilityKeyT = "can_activate_course"
    CAN_VIEW_COURSE_OPERATION_LOG: UserAuthorityCapabilityKeyT = (
        "can_view_course_operation_log"
    )
    CAN_VIEW_ASYNC_JOB_HISTORY: UserAuthorityCapabilityKeyT = (
        "can_view_async_job_history"
    )
    CAN_VIEW_COURSE_PUBLISHED: UserAuthorityCapabilityKeyT = "can_view_course_published"
    CAN_VIEW_COURSE: UserAuthorityCapabilityKeyT = "can_view_course"
    CAN_EDIT_COURSE: UserAuthorityCapabilityKeyT = "can_edit_course"
    CAN_CREATE_EXERCISE: UserAuthorityCapabilityKeyT = "can_create_exercise"
    CAN_VIEW_EXERCISE_PUBLISHED: UserAuthorityCapabilityKeyT = (
        "can_view_exercise_published"
    )
    CAN_VIEW_EXERCISE_UNTIL_END: UserAuthorityCapabilityKeyT = (
        "can_view_exercise_until_end"
    )
    CAN_VIEW_EXERCISE: UserAuthorityCapabilityKeyT = "can_view_exercise"
    CAN_EDIT_EXERCISE: UserAuthorityCapabilityKeyT = "can_edit_exercise"
    CAN_CONFIRM_SUBMISSION: UserAuthorityCapabilityKeyT = "can_confirm_submission"
    CAN_REVIEW_SUBMISSION: UserAuthorityCapabilityKeyT = "can_review_submission"
    CAN_LIST_SUBMISSION: UserAuthorityCapabilityKeyT = "can_list_submission"
    CAN_SUBMIT_SUBMISSION: UserAuthorityCapabilityKeyT = "can_submit_submission"
    CAN_REJUDGE_SUBMISSION: UserAuthorityCapabilityKeyT = "can_rejudge_submission"


UserAuthorityKeyT = Union[
    Literal["on_organization"],
    Literal["on_course"],
    UserAuthorityCapabilityKeyT,
]


def __build_slack_exception_message(request: HttpRequest, issue: str) -> str:
    return (
        f"On: {request.build_absolute_uri()}\n"
        f"By: {request.user.username} ({request.user.id})\n"
        f"Issue: Detected {issue}"
    )


_PCheckUserAuthority = ParamSpec("_PCheckUserAuthority")
_TViewFunc: TypeAlias = Callable[
    Concatenate[HttpRequest, UserAuthorityDict, _PCheckUserAuthority], HttpResponse
]

_PPureViewFunc = ParamSpec("_PPureViewFunc")
_TPureViewFunc: TypeAlias = Callable[
    Concatenate[HttpRequest, _PPureViewFunc], HttpResponse
]


def check_and_notify_exception(
    view_func: _TPureViewFunc[_PPureViewFunc],
) -> _TPureViewFunc[_PPureViewFunc]:
    """
    Decorator for views that may throw an exception.
    This intercepts an exception, notify it to slack, then throw it again to its caller.
    """

    @wraps(view_func)
    def _wrapped_view(
        request: HttpRequest, *args: DjangoRequestArg, **kwargs: DjangoRequestKwarg
    ) -> HttpResponse:
        try:
            return view_func(request, *args, **kwargs)
        except PermissionDenied:
            message = __build_slack_exception_message(request, "PermissionDenied")
            SLACK_NOTIFIER.warning(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            raise
        except UserResponsibleException:
            message = __build_slack_exception_message(
                request, "UserResponsibleException"
            )
            SLACK_NOTIFIER.warning(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            raise
        except SystemResponsibleException:
            message = __build_slack_exception_message(
                request, "SystemResponsibleException"
            )
            SLACK_NOTIFIER.error(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            raise
        except Exception:  # pylint:disable=broad-except
            message = __build_slack_exception_message(request, "BaseException")
            SLACK_NOTIFIER.critical(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            raise

    return _wrapped_view


def annex_user_authority(
    view_func: _TPureViewFunc[_PPureViewFunc],
) -> _TViewFunc[_PCheckUserAuthority]:
    """
    Decorator for views that add the user authority information to view function argument.
    This authority information is added just after `request` argument.
    """

    @wraps(view_func)
    def _wrapped_view(
        request: HttpRequest, *args: DjangoRequestArg, **kwargs: DjangoRequestKwarg
    ) -> HttpResponse:
        user_authority = get_user_authority(request, *args, **kwargs)
        # print(user_authority)
        return view_func(request, user_authority, *args, **kwargs)

    return _wrapped_view


def check_user_capability(
    user_authority: UserAuthorityDict,
    test_capability: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ],
) -> bool:
    if isinstance(test_capability, str):
        if test_capability in user_authority:
            return user_authority[test_capability]
    if isinstance(test_capability, tuple):
        return any(
            check_user_capability(user_authority, cap) for cap in test_capability
        )
    SLACK_NOTIFIER.critical(  # type:ignore[unreachable]
        f"LogicalError: unregistered capability: {test_capability=!r} (fallback to False)",
        tracebacks=traceback.format_exc(),
    )
    return False


def raise_if_lacks_user_authority(
    request: HttpRequest,
    user_authority: UserAuthorityDict,
    test_capability: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ],
) -> None:
    if check_user_capability(user_authority, test_capability):
        return
    path = request.build_absolute_uri()
    resolved_login_url = resolve_url("login")
    # If the login url is the same scheme and net location then just
    # use the path as the "next" url.
    login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
    current_scheme, current_netloc = urlparse(path)[:2]
    if (not login_scheme or login_scheme == current_scheme) and (
        not login_netloc or login_netloc == current_netloc
    ):
        path = request.get_full_path()
    try:
        request_user_str = str(request.user)
    except TypeError:
        # TypeError: __str__ returned non-string (type NoneType)
        # email=None の場合に発生する
        request_user_str = f"<User id={request.user.id}>"
    raise PermissionDenied(f"request.user={request_user_str} has no {test_capability=}")


# def check_user_authority(test_func, login_url=None, redirect_field_name=REDIRECT_FIELD_NAME):
def check_user_authority(
    test_capability: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ],
) -> Callable[[_TViewFunc[_PCheckUserAuthority]], _TViewFunc[_PCheckUserAuthority]]:
    """
    Decorator for views that checks that the user have enough authority to do some action.
    If it is not enough, redirects to the log-in page.
    The test should be a callable that takes the user object, *args and **kwargs,
    then returns True if the user have enough authority.

    Please keep in mind that this must be called after `annex_user_authority` defined above.
    """

    def decorator(
        view_func: _TViewFunc[_PCheckUserAuthority],
    ) -> _TViewFunc[_PCheckUserAuthority]:
        @wraps(view_func)
        def _wrapped_view(
            request: HttpRequest,
            user_authority: UserAuthorityDict,
            *args: DjangoRequestArg,
            **kwargs: DjangoRequestKwarg,
        ) -> HttpResponse:
            raise_if_lacks_user_authority(request, user_authority, test_capability)
            return view_func(request, user_authority, *args, **kwargs)

        return _wrapped_view

    return decorator


class UserType(enum.Enum):
    STAFF = 10
    ACTIVE = 20
    TRANSITORY = 30
    INACTIVE = 50


def _check_user_type(user: User) -> UserType:
    if not user.is_active:
        return UserType.INACTIVE
    if user.is_superuser or user.is_staff:
        return UserType.STAFF
    if user.is_transitory():
        return UserType.TRANSITORY
    return UserType.ACTIVE


USER_AUTHORITY_KEYS: Tuple[UserAuthorityKeyT, ...] = (
    "on_organization",
    "on_course",
)

# .data.
# .seen_from.

# CRUD: create, read, update, delete
# can_see_existence or not

USER_AUTHORITY_CAPABILITY_KEYS: Tuple[UserAuthorityCapabilityKeyT, ...] = (
    "can_invite_user",
    "can_invite_user_to_organization",
    "can_manage_user",
    "can_manage_organization_user",
    "can_manage_course_user",
    # 'can_create_organization',
    # 'can_activate_organization',
    "can_view_organization",
    "can_edit_organization",
    "can_create_course",
    # 'can_activate_course',
    "can_view_course_operation_log",
    "can_view_async_job_history",
    "can_view_course_published",
    "can_view_course",
    "can_edit_course",
    "can_create_exercise",
    "can_view_exercise_published",
    "can_view_exercise_until_end",
    "can_view_exercise",
    "can_edit_exercise",
    "can_confirm_submission",
    "can_review_submission",
    "can_list_submission",
    "can_submit_submission",
    "can_rejudge_submission",
)

USER_AUTHORITY_FOR_STAFF: Final[UserAuthorityDict] = dict(  # type: ignore[misc,assignment] # noqa:E501
    is_superuser=True,
    is_faculty=True,
    is_active=True,
    is_transitory=False,
    has_no_authority=False,
    **{key: UserAuthorityEnum.MANAGER for key in USER_AUTHORITY_KEYS},
    **{key: True for key in USER_AUTHORITY_CAPABILITY_KEYS},
)
# NOTE TRANSITORY 状態 ⇔ 「自力で ACTIVE 状態に遷移可能な READONLY 状態」
USER_AUTHORITY_FOR_TRANSITORY: Final[UserAuthorityDict] = dict(  # type: ignore[misc,assignment] # noqa:E501
    is_superuser=False,
    is_faculty=False,
    is_active=False,
    is_transitory=True,
    has_no_authority=True,
    **{key: UserAuthorityEnum.READONLY for key in USER_AUTHORITY_KEYS},
    **{key: False for key in USER_AUTHORITY_CAPABILITY_KEYS},
)
USER_AUTHORITY_FOR_READONLY: Final[UserAuthorityDict] = dict(  # type: ignore[misc,assignment] # noqa:E501
    is_superuser=False,
    is_faculty=False,
    is_active=False,
    is_transitory=False,
    has_no_authority=True,
    **{key: UserAuthorityEnum.READONLY for key in USER_AUTHORITY_KEYS},
    **{key: False for key in USER_AUTHORITY_CAPABILITY_KEYS},
)


def get_user_authority(
    request: HttpRequest, *args: DjangoRequestArg, **kwargs: DjangoRequestKwarg
) -> UserAuthorityDict:
    """
    ユーザーの権限を取得し、辞書の形式で返す
    """
    del args

    request_user = get_request_user_safe(request)

    user_type = _check_user_type(request_user)
    if user_type == UserType.STAFF:
        return USER_AUTHORITY_FOR_STAFF
    if user_type == UserType.TRANSITORY:
        return USER_AUTHORITY_FOR_TRANSITORY
    if user_type == UserType.INACTIVE:
        return USER_AUTHORITY_FOR_READONLY

    def _get_organization_course_authority() -> (
        Tuple[UserAuthorityEnum, UserAuthorityEnum]
    ):
        organization_authority: UserAuthorityEnum = UserAuthorityEnum.READONLY
        course_authority: UserAuthorityEnum = UserAuthorityEnum.READONLY

        if "o_name" in kwargs:
            organization = get_organization(**kwargs)
            with contextlib.suppress(OrganizationUser.DoesNotExist):
                organization_authority = UserAuthorityEnum(
                    OrganizationUser.objects.get(
                        organization=organization, user=request_user, is_active=True
                    ).authority
                )

            if "c_name" in kwargs:
                _o, course = get_course(organization, **kwargs)
                with contextlib.suppress(CourseUser.DoesNotExist):
                    course_authority = UserAuthorityEnum(
                        CourseUser.objects.get(
                            course=course, user=request_user, is_active=True
                        ).authority
                    )

        return organization_authority, max(organization_authority, course_authority)

    organization_authority, course_authority = _get_organization_course_authority()

    has_no_authority = (
        organization_authority == course_authority == UserAuthorityEnum.READONLY
    )

    return _get_user_authority_impl(
        organization_authority,
        course_authority,
        is_faculty=request_user.is_faculty,
        is_active=request_user.is_active and not request_user.is_transitory(),
        is_transitory=request_user.is_transitory(),
        has_no_authority=has_no_authority,
    )


def _get_user_authority_impl(
    organization_authority: UserAuthorityEnum,
    course_authority: UserAuthorityEnum,
    *,
    is_faculty: bool,
    is_active: bool,
    is_transitory: bool,
    has_no_authority: bool,
) -> UserAuthorityDict:
    return {
        "is_superuser": False,
        "is_faculty": is_faculty,
        "is_active": is_active,
        "is_transitory": is_transitory,
        "has_no_authority": has_no_authority,
        "on_organization": organization_authority,
        "on_course": course_authority,
        "can_invite_user": False,  # Staff-only
        "can_invite_user_to_organization": UserAuthorityEnum.MANAGER
        <= organization_authority,
        "can_manage_user": False,  # Staff-only
        "can_manage_organization_user": UserAuthorityEnum.MANAGER
        <= organization_authority,
        "can_manage_course_user": UserAuthorityEnum.MANAGER <= course_authority,
        # 'can_create_organization': UserAuthorityEnum.MANAGER,
        # 'can_activate_organization': UserAuthorityEnum.MANAGER,
        "can_edit_organization": UserAuthorityEnum.LECTURER <= organization_authority,
        "can_view_organization": UserAuthorityEnum.READONLY < organization_authority,
        "can_create_course": UserAuthorityEnum.MANAGER <= organization_authority,
        # 'can_activate_course': UserAuthorityEnum.MANAGER,
        "can_view_course_operation_log": UserAuthorityEnum.MANAGER
        <= organization_authority,
        "can_view_async_job_history": UserAuthorityEnum.LECTURER <= course_authority,
        "can_view_course_published": UserAuthorityEnum.READONLY < course_authority,
        "can_view_course": UserAuthorityEnum.ASSISTANT <= course_authority,
        "can_edit_course": UserAuthorityEnum.LECTURER <= course_authority,
        "can_create_exercise": UserAuthorityEnum.MANAGER <= course_authority,
        "can_view_exercise_published": UserAuthorityEnum.READONLY < course_authority,
        "can_view_exercise_until_end": UserAuthorityEnum.ASSISTANT <= course_authority,
        "can_view_exercise": UserAuthorityEnum.LECTURER <= course_authority,
        "can_edit_exercise": UserAuthorityEnum.LECTURER <= course_authority,
        "can_confirm_submission": UserAuthorityEnum.LECTURER <= course_authority,
        "can_review_submission": UserAuthorityEnum.ASSISTANT <= course_authority,
        "can_list_submission": UserAuthorityEnum.STUDENT <= course_authority,
        "can_submit_submission": UserAuthorityEnum.ANONYMOUS <= course_authority,
        "can_rejudge_submission": UserAuthorityEnum.MANAGER <= course_authority,
    }


# USER_AUTHORITY_FOR_STAFF = _get_user_authority_impl(
#     UserAuthorityEnum.READONLY,
#     # UserAuthorityEnum.MANAGER,
#     UserAuthorityEnum.ASSISTANT,
#     # UserAuthorityEnum.STUDENT,
#     is_faculty=False,
#     is_active=True,
#     is_transitory=False,
#     has_no_authority=False,
# )


def get_user_authority_on_organization(
    user: User, organization: Organization
) -> UserAuthorityEnum:
    user_type = _check_user_type(user)
    if user_type == UserType.STAFF:
        return UserAuthorityEnum.MANAGER
    if user_type == UserType.INACTIVE:
        return UserAuthorityEnum.READONLY
    # ここまでテンプレ

    organization_authority: UserAuthorityEnum = UserAuthorityEnum.READONLY
    organization_user = OrganizationUser.objects.filter(
        organization=organization, user=user
    ).first()
    if organization_user is not None:
        organization_authority = UserAuthorityEnum(organization_user.authority)
    return organization_authority


def get_user_authority_on_course(
    user: User, organization: Organization, course: Course
) -> UserAuthorityEnum:
    user_type = _check_user_type(user)
    if user_type == UserType.STAFF:
        return UserAuthorityEnum.MANAGER
    if user_type == UserType.INACTIVE:
        return UserAuthorityEnum.READONLY
    # ここまでテンプレ

    organization_user = OrganizationUser.objects.filter(
        organization=organization, user=user
    ).first()
    organization_authority: UserAuthorityEnum = UserAuthorityEnum.READONLY
    if organization_user is not None:
        organization_authority = UserAuthorityEnum(organization_user.authority)

    course_user = CourseUser.objects.filter(course=course, user=user).first()
    course_authority: UserAuthorityEnum = UserAuthorityEnum.READONLY
    if course_user is not None:
        course_authority = UserAuthorityEnum(course_user.authority)

    return max(organization_authority, course_authority)


# def ip_limited(*, allow_ip_list: list = None, deny_ip_list: list = None):
#     """
#     Decorator for limited IP that allows to access.
#     """

#     def decorator(view_func):
#         @wraps(view_func)
#         def _wrapped_view(request, *args, **kwargs):
#             if deny_ip_list and request.META['REMOTE_ADDR'] in deny_ip_list:
#                 raise Http404()
#             if allow_ip_list and request.META['REMOTE_ADDR'] not in allow_ip_list:
#                 raise Http404()
#             return view_func(request, *args, **kwargs)
#         return _wrapped_view
#     return decorator


@dataclasses.dataclass
class ContextUserAuthority:
    is_superuser: bool
    is_faculty: bool
    is_active: bool
    is_transitory: bool
    has_no_authority: bool
    can_invite_user: bool
    can_invite_user_to_organization: bool
    can_manage_user: bool
    can_manage_organization_user: bool
    can_manage_course_user: bool
    # can_create_organization: bool
    # can_activate_organization: bool
    can_edit_organization: bool
    can_view_organization: bool
    can_create_course: bool
    # can_activate_course: bool
    can_view_course_published: bool
    can_view_course: bool
    can_edit_course: bool
    can_create_exercise: bool
    can_view_exercise_published: bool
    can_view_exercise_until_end: bool
    can_view_exercise: bool
    can_edit_exercise: bool
    can_confirm_submission: bool
    can_review_submission: bool
    can_list_submission: bool
    can_submit_submission: bool
    can_rejudge_submission: bool

    @staticmethod
    def from_legacy(user_authority: UserAuthorityDict) -> "ContextUserAuthority":
        return ContextUserAuthority(
            is_superuser=user_authority["is_superuser"],
            is_faculty=user_authority["is_faculty"],
            is_active=user_authority["is_active"],
            is_transitory=user_authority["is_transitory"],
            has_no_authority=user_authority["has_no_authority"],
            can_invite_user=user_authority["can_invite_user"],
            can_invite_user_to_organization=user_authority[
                "can_invite_user_to_organization"
            ],
            can_manage_user=user_authority["can_manage_user"],
            can_manage_organization_user=user_authority["can_manage_organization_user"],
            can_manage_course_user=user_authority["can_manage_course_user"],
            # can_create_organization: bool
            # can_activate_organization: bool
            can_edit_organization=user_authority["can_edit_organization"],
            can_view_organization=user_authority["can_view_organization"],
            can_create_course=user_authority["can_create_course"],
            # can_activate_course: bool
            can_view_course_published=user_authority["can_view_course_published"],
            can_view_course=user_authority["can_view_course"],
            can_edit_course=user_authority["can_edit_course"],
            can_create_exercise=user_authority["can_create_exercise"],
            can_view_exercise_published=user_authority["can_view_exercise_published"],
            can_view_exercise_until_end=user_authority["can_view_exercise_until_end"],
            can_view_exercise=user_authority["can_view_exercise"],
            can_edit_exercise=user_authority["can_edit_exercise"],
            can_confirm_submission=user_authority["can_confirm_submission"],
            can_review_submission=user_authority["can_review_submission"],
            can_list_submission=user_authority["can_list_submission"],
            can_submit_submission=user_authority["can_submit_submission"],
            can_rejudge_submission=user_authority["can_rejudge_submission"],
        )


@dataclasses.dataclass
class RequestContext:
    request: HttpRequest
    organization: Optional[Organization]
    course: Optional[Course]
    user_authority: ContextUserAuthority
    user_authority_on_organization: UserAuthorityEnum
    user_authority_on_course: UserAuthorityEnum

    @staticmethod
    def from_legacy(
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Optional[Organization] = None,
        course: Optional[Course] = None,
    ) -> "RequestContext":
        return RequestContext(
            request=request,
            organization=organization,
            course=course,
            user_authority=ContextUserAuthority.from_legacy(user_authority),
            user_authority_on_organization=user_authority["on_organization"],
            user_authority_on_course=user_authority["on_course"],
        )


def get_context(
    request: HttpRequest, organization_name: Optional[str], course_name: Optional[str]
) -> RequestContext:
    """
    コンテキスト（組織、コース、ユーザーの権限など）を取得し返す

    NOTE 一旦API向けに作るが、将来的にはこれで統一したい
    """
    request_user = get_request_user_safe(request)

    organization, course = None, None
    if organization_name is not None:
        organization = get_organization(o_name=organization_name)
        if course_name is not None:
            _o, course = get_course(organization, c_name=course_name)

    organization_authority: UserAuthorityEnum = UserAuthorityEnum.READONLY
    course_authority: UserAuthorityEnum = UserAuthorityEnum.READONLY

    if organization is not None:
        with contextlib.suppress(OrganizationUser.DoesNotExist):
            organization_authority = UserAuthorityEnum(
                OrganizationUser.objects.get(
                    organization=organization, user=request_user, is_active=True
                ).authority
            )

    if course is not None:
        with contextlib.suppress(CourseUser.DoesNotExist):
            course_authority = UserAuthorityEnum(
                CourseUser.objects.get(
                    course=course, user=request_user, is_active=True
                ).authority
            )

    course_authority = max(organization_authority, course_authority)

    # 特定の強い条件下では無視して上書きする
    user_type = _check_user_type(request_user)
    if user_type == UserType.STAFF:
        if organization is not None:
            organization_authority = UserAuthorityEnum.MANAGER
        if course is not None:
            course_authority = UserAuthorityEnum.MANAGER
    elif user_type in (UserType.INACTIVE, UserType.TRANSITORY):
        if organization is not None:
            organization_authority = UserAuthorityEnum.READONLY
        if course is not None:
            course_authority = UserAuthorityEnum.READONLY

    has_no_authority = (
        organization_authority == course_authority == UserAuthorityEnum.READONLY
    )

    user_authority = ContextUserAuthority(
        is_superuser=user_type == UserType.STAFF,
        is_faculty=request_user.is_faculty,
        is_active=request_user.is_active and not request_user.is_transitory(),
        is_transitory=request_user.is_transitory(),
        has_no_authority=has_no_authority,
        can_invite_user=user_type == UserType.STAFF,
        can_invite_user_to_organization=UserAuthorityEnum.MANAGER
        <= organization_authority,
        can_manage_user=user_type == UserType.STAFF,
        can_manage_organization_user=UserAuthorityEnum.MANAGER
        <= organization_authority,
        can_manage_course_user=UserAuthorityEnum.MANAGER <= course_authority,
        # can_create_organization=UserAuthorityEnum.MANAGER,
        # can_activate_organization=UserAuthorityEnum.MANAGER,
        can_edit_organization=UserAuthorityEnum.LECTURER <= organization_authority,
        can_view_organization=UserAuthorityEnum.READONLY < organization_authority,
        can_create_course=UserAuthorityEnum.MANAGER <= organization_authority,
        # can_activate_course=UserAuthorityEnum.MANAGER,
        can_view_course_published=UserAuthorityEnum.READONLY < course_authority,
        can_view_course=UserAuthorityEnum.ASSISTANT <= course_authority,
        can_edit_course=UserAuthorityEnum.LECTURER <= course_authority,
        can_create_exercise=UserAuthorityEnum.MANAGER <= course_authority,
        can_view_exercise_published=UserAuthorityEnum.READONLY < course_authority,
        can_view_exercise_until_end=UserAuthorityEnum.ASSISTANT <= course_authority,
        can_view_exercise=UserAuthorityEnum.LECTURER <= course_authority,
        can_edit_exercise=UserAuthorityEnum.LECTURER <= course_authority,
        can_confirm_submission=UserAuthorityEnum.LECTURER <= course_authority,
        can_review_submission=UserAuthorityEnum.ASSISTANT <= course_authority,
        can_list_submission=UserAuthorityEnum.STUDENT <= course_authority,
        can_submit_submission=UserAuthorityEnum.ANONYMOUS <= course_authority,
        can_rejudge_submission=UserAuthorityEnum.MANAGER <= course_authority,
    )

    return RequestContext(
        request=request,
        organization=organization,
        course=course,
        user_authority=user_authority,
        user_authority_on_organization=organization_authority,
        user_authority_on_course=course_authority,
    )


def annex_context(func):
    """
    Decorator for views that add the user authority information to view function argument.
    This authority information is added just after `request` argument.
    """

    @wraps(func)
    def _wrapped_view(request, *_args, **kwargs):
        organization_name = kwargs.get("o_name")
        course_name = kwargs.get("c_name")
        context = get_context(
            request,
            organization_name=organization_name,
            course_name=course_name,
        )
        # print(context)
        return func(context)

    return _wrapped_view


def check_context_user_capability(
    context: RequestContext,
    capability: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ],
) -> bool:
    if isinstance(capability, str):
        return getattr(context.user_authority, capability)
    if isinstance(capability, tuple):
        return any(check_context_user_capability(context, cap) for cap in capability)
    SLACK_NOTIFIER.critical(
        f"LogicalError: {capability=!r}", tracebacks=traceback.format_exc()
    )
    return False


# def check_context_user_authority(test_func, login_url=None, redirect_field_name=REDIRECT_FIELD_NAME):
def check_context_user_authority(
    capability: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ],
    login_url=None,
):
    """
    Decorator for views that checks that the user have enough authority to do some action.
    If it is not enough, redirects to the log-in page.
    The test should be a callable that takes the user object, *args and **kwargs,
    then returns True if the user have enough authority.

    Please keep in mind that this must be called after `annex_user_authority` defined above.
    """

    def decorator(func):
        @wraps(func)
        def _wrapped_view(context, *args, **kwargs):
            if check_context_user_capability(context, capability):
                return func(context, *args, **kwargs)
            path = context.request.build_absolute_uri()
            resolved_login_url = resolve_url(login_url or "login")
            # If the login url is the same scheme and net location then just
            # use the path as the "next" url.
            login_scheme, login_netloc = urlparse(resolved_login_url)[:2]
            current_scheme, current_netloc = urlparse(path)[:2]
            if (not login_scheme or login_scheme == current_scheme) and (
                not login_netloc or login_netloc == current_netloc
            ):
                path = context.request.get_full_path()
            print(context)
            raise PermissionDenied(f"{context.request.user=} has no {capability=}")
            # from django.contrib.auth.views import redirect_to_login
            # return redirect_to_login(
            #     path, resolved_login_url, redirect_field_name)

        return _wrapped_view

    return decorator


def check_and_notify_api_exception(func):
    """
    Decorator for views that may throw an exception.
    This intercepts an exception, notify it to slack, then throw it again to its caller.
    """

    def _error_response(error_type: str, message: str):
        return api_error_response(
            [
                ApiErrorData(
                    loc=["__main__"],
                    msg=message,
                    type=error_type,
                )
            ]
        )

    @wraps(func)
    def _wrapped_api_call(context, *args, **kwargs):
        try:
            return func(context, *args, **kwargs)
        except PermissionDenied:
            message = __build_slack_exception_message(
                context.request, "PermissionDenied"
            )
            SLACK_NOTIFIER.warning(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            return _error_response("PermissionDenied", "Permission Denied")
        except UserResponsibleException as exc:
            message = __build_slack_exception_message(
                context.request, "UserResponsibleException"
            )
            SLACK_NOTIFIER.warning(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            return _error_response("UserResponsibleException", exc.get_user_message())
        except SystemResponsibleException as exc:
            message = __build_slack_exception_message(
                context.request, "SystemResponsibleException"
            )
            SLACK_NOTIFIER.error(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            return _error_response(
                "SystemResponsibleException", exc.get_user_message("__process__")
            )
        except Exception:  # pylint: disable=broad-except
            message = __build_slack_exception_message(context.request, "BaseException")
            SLACK_NOTIFIER.critical(message, tracebacks=traceback.format_exc())
            traceback.print_exc()
            return _error_response("InternalServerError", "Internal Server Error")

    return _wrapped_api_call


def check_user_authority_without_args(
    test_capability: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ],
    *,
    require_active_account: bool = True,
) -> Callable[[_TViewFunc[_PCheckUserAuthority]], _TViewFunc[_PCheckUserAuthority]]:
    """`check_user_authority` の `annex_user_authority` なし版"""


    def decorator(
        view_func: _TViewFunc[_PCheckUserAuthority],
    ) -> _TViewFunc[_PCheckUserAuthority]:
        @wraps(view_func)
        def _wrapped_view(
            request: HttpRequest, *args: DjangoRequestArg, **kwargs: DjangoRequestKwarg
        ) -> HttpResponse:
            user_authority: UserAuthorityDict = get_user_authority(
                request, *args, **kwargs
            )
            if require_active_account:
                raise_if_lacks_user_authority(
                    request, user_authority, UserAuthorityCapabilityKeys.IS_ACTIVE
                )
            raise_if_lacks_user_authority(request, user_authority, test_capability)
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
