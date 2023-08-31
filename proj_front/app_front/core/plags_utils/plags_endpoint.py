import dataclasses
import inspect
from abc import ABCMeta, abstractmethod
from typing import _GenericAlias  # type:ignore
from typing import (
    Any,
    Callable,
    Dict,
    Final,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    get_args,
    get_origin,
)

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http.request import HttpRequest
from django.http.response import Http404, HttpResponse
from django.views import View
from typing_extensions import Concatenate, ParamSpec

from app_front.core.develop import with_profile
from app_front.core.types import DjangoRequestArg, DjangoRequestKwarg
from app_front.models import (
    Course,
    CourseTopNoticeByOrganization,
    CustomEvaluationTag,
    Exercise,
    Organization,
    Submission,
    SubmissionParcel,
    User,
)
from app_front.utils.auth_util import (
    UserAuthorityCapabilityKeys,
    UserAuthorityCapabilityKeyT,
    UserAuthorityDict,
    check_and_notify_exception,
    check_user_authority_without_args,
    get_user_authority,
)
from app_front.utils.exception_util import SystemLogicalError
from app_front.utils.parameter_decoder import (
    get_organization,
    get_organization_course,
    get_organization_course_custom_evaluation_tag,
    get_organization_course_exercise,
    get_organization_course_submission_parcel,
    get_organization_course_top_notice_by_organization,
    get_submission,
    get_user,
)

_PDjangoViewEndpoint = ParamSpec("_PDjangoViewEndpoint")
_TDjangoViewEndpointFunc = Callable[
    Concatenate[HttpRequest, _PDjangoViewEndpoint],
    HttpResponse,
]

_TAnnotateViewEndpointFunc = Callable[..., HttpResponse]

EndpointParameterName = str
EndpointParameterType = type


@dataclasses.dataclass
class EndpointParameter:
    name: EndpointParameterName
    type: EndpointParameterType
    is_optional: bool

    @classmethod
    def from_inspect_parameter(
        cls, parameter: inspect.Parameter
    ) -> "EndpointParameter":
        # param: 型 のアノテーション
        if isinstance(parameter.annotation, type):
            return EndpointParameter(
                name=parameter.name, type=parameter.annotation, is_optional=False
            )
        # param: Optional[型] のアノテーション
        if all(
            (
                isinstance(parameter.annotation, _GenericAlias),
                # NOTE OptionalはUnionに変換されるのでこれで正しい
                get_origin(parameter.annotation) is Union,
                len(annotation_args := get_args(parameter.annotation)) == 2,
                isinstance(annotation_args[0], type),
                annotation_args[1] is type(None),
            )
        ):
            return EndpointParameter(
                name=parameter.name, type=annotation_args[0], is_optional=True
            )
        # NOTE ForwardRefだったらつらい なる使い方は現状ないはずなので一旦考えない
        raise SystemLogicalError("Invalid type annotation")


@dataclasses.dataclass
class ViewEndpointAnnotationData:
    require_login: bool
    require_capabilities: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ]
    require_active_account: bool
    require_parameters: Tuple[EndpointParameter, ...]
    profile_save_elapse_threshold: Optional[float]


class _Optional_Organization:
    pass


class _Optional_Course:
    pass


_PDjangoViewFunc = ParamSpec("_PDjangoViewFunc")
DjangoViewFunc = Callable[Concatenate[HttpRequest, _PDjangoViewFunc], HttpResponse]
DjangoViewFuncArg = Union[
    int,
    str,
    HttpRequest,
    User,
    Organization,
    _Optional_Organization,
    Course,
    _Optional_Course,
    Exercise,
    SubmissionParcel,
    Submission,
    CustomEvaluationTag,
    CourseTopNoticeByOrganization,
    UserAuthorityDict,
]
_DJANGO_VIEW_FUNC_ARG_OPTIONAL_MAPPING: Final[
    Dict[Type[DjangoViewFuncArg], Type[DjangoViewFuncArg]]
] = {
    Organization: _Optional_Organization,
    Course: _Optional_Course,
}


def annotate_view_endpoint(
    require_login: bool = True,
    require_capabilities: Union[
        UserAuthorityCapabilityKeyT, Tuple[UserAuthorityCapabilityKeyT, ...]
    ] = (),
    require_active_account: Optional[bool] = None,
    profile_save_elapse_threshold: Optional[float] = None,
) -> Callable[[_TAnnotateViewEndpointFunc], _TAnnotateViewEndpointFunc]:
    """
    ビューのエンドポイントとなる関数に付与することで、
    関数にメタデータを含む属性 `__view_endpoint_annotations__` を付与する。

    含むメタデータは以下の通り:

    * ログインを要求するか（`require_login`）
    * 権限を要求するか（`require_capabilities`）
    * 有効なアカウントを要求するか（`require_active_account`）
    * 関数引数（要求に応じて裏側でバリデーション・取得処理を行う）

    NOTE ビューに限らないように（普通のAPIの時にも共用できるように e.g. FastAPI）設計していきたい
    """

    # NOTE require_active_account は require_login と一致させるのが普通であるが、稀に False にしたい場合もある
    require_active_account_bool: bool
    if require_active_account is None:
        require_active_account_bool = require_login
    else:
        require_active_account_bool = require_active_account
        if not require_login:
            assert (
                not require_active_account
            ), "Invalid setting: login is optional but active account is required."

    def decorator(func: _TAnnotateViewEndpointFunc) -> _TAnnotateViewEndpointFunc:
        signature = inspect.signature(func)
        require_parameters: List[EndpointParameter] = []
        for idx, parameter in enumerate(signature.parameters.values()):
            if idx == 0 and parameter.name in ("cls", "self"):
                continue
            if parameter.kind not in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                # NOTE 現状ではパスパラメータについてのみ処理しているため弾いているが、将来クエリパラメータに対応する場合
                #      これを使うのが自然に思われる。その時が来たら作る。
                raise SystemLogicalError(
                    f"non-positional argument is not allowed in view endpoints for now (on {parameter}, {func})"
                )
            if parameter.default is not inspect.Parameter.empty:
                raise SystemLogicalError(
                    f"positional arguments (path-parameters) accepts no default value (on {parameter}, {func})"
                )
            try:
                endpoint_parameter = EndpointParameter.from_inspect_parameter(parameter)
            except SystemLogicalError as exc:
                raise SystemLogicalError(
                    f"positional argument (path-parameters) must have valid type annotations (on {parameter}, {func})"
                ) from exc
            if endpoint_parameter.type not in get_args(DjangoViewFuncArg):
                raise SystemLogicalError(
                    f"unexpected type for parameter (on {parameter}, {func})"
                )
            if endpoint_parameter.is_optional:
                if (
                    endpoint_parameter.type
                    not in _DJANGO_VIEW_FUNC_ARG_OPTIONAL_MAPPING
                ):
                    raise SystemLogicalError(
                        f"unexpected type for parameter (on {parameter}, {func})"
                    )
                endpoint_parameter.type = _DJANGO_VIEW_FUNC_ARG_OPTIONAL_MAPPING[
                    endpoint_parameter.type
                ]
            require_parameters.append(endpoint_parameter)

        view_endpoint_annotations = ViewEndpointAnnotationData(
            require_login=require_login,
            require_capabilities=require_capabilities,
            require_active_account=require_active_account_bool,
            require_parameters=tuple(require_parameters),
            profile_save_elapse_threshold=profile_save_elapse_threshold,
        )
        setattr(func, "__view_endpoint_annotations__", view_endpoint_annotations)
        return func

    return decorator


class AbsPlagsEndpointArgumentGetter(metaclass=ABCMeta):
    def __init__(self, parameter: EndpointParameter) -> None:
        self._parameter = parameter

    @abstractmethod
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> DjangoViewFuncArg:
        raise NotImplementedError


class PlagsEndpointStrArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> str:
        del args
        if self._parameter.name not in kwargs:
            raise SystemLogicalError(f"parameter {self._parameter.name=!r} is missing")
        value = kwargs[self._parameter.name]
        if not isinstance(value, str):
            raise ValidationError(f"invalid {value=!r}")
        return value


class PlagsEndpointIntArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> int:
        del args
        if self._parameter.name not in kwargs:
            raise SystemLogicalError(f"parameter {self._parameter.name=!r} is missing")
        value = kwargs[self._parameter.name]
        try:
            return int(value)
        except ValueError as exc:
            raise ValidationError(f"invalid {value=!r}") from exc


class PlagsEndpointHttpRequestArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> HttpRequest:
        return request


# def get_first_existing_key(param: Dict[str, Any], *args: str) -> Optional[str]:
#     for arg in args:
#         if arg in param:
#             return arg
#     return None


class PlagsEndpointUserArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> User:
        del request, args
        return get_user(**kwargs)


class PlagsEndpointOrganizationArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> Organization:
        del request, args
        return get_organization(**kwargs)
        # if (appropriate_key := get_first_existing_key(kwargs, self._parameter.name, "o_name")) is None:
        #     raise SystemLogicalError(f"parameter {self._parameter.name=!r} is missing")
        # value = kwargs[appropriate_key]
        # if not isinstance(value, str):
        #     raise ValidationError(f"invalid {value=!r}")
        # return ...


class PlagsEndpointOptionalOrganizationArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> Optional[Organization]:
        del request, args
        try:
            return get_organization(**kwargs)
        except Http404:
            return None


class PlagsEndpointCourseArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> Course:
        del request, args
        _organization, course = get_organization_course(**kwargs)
        return course


class PlagsEndpointOptionalCourseArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> Optional[Course]:
        del request, args
        try:
            _organization, course = get_organization_course(**kwargs)
            return course
        except Http404:
            return None


class PlagsEndpointExerciseArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> Exercise:
        del request, args
        _organization, _course, exercise = get_organization_course_exercise(**kwargs)
        return exercise


class PlagsEndpointSubmissionParcelArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> SubmissionParcel:
        del request, args
        (
            _organization,
            _course,
            submission_parcel,
        ) = get_organization_course_submission_parcel(**kwargs)
        return submission_parcel


class PlagsEndpointSubmissionArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> Submission:
        del request, args
        organization, course = get_organization_course(**kwargs)
        _organization, _course, submission = get_submission(
            organization, course, **kwargs
        )
        return submission


class PlagsEndpointCustomEvaluationTagArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> CustomEvaluationTag:
        del request, args
        (
            _organization,
            _course,
            custom_evaluation_tag,
        ) = get_organization_course_custom_evaluation_tag(**kwargs)
        return custom_evaluation_tag


class PlagsEndpointCourseTopNoticeByOrganizationArgumentGetter(
    AbsPlagsEndpointArgumentGetter
):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> CourseTopNoticeByOrganization:
        del request, args
        (
            _organization,
            course_top_notice_by_organization,
        ) = get_organization_course_top_notice_by_organization(**kwargs)
        return course_top_notice_by_organization


class PlagsEndpointUserAuthorityDictArgumentGetter(AbsPlagsEndpointArgumentGetter):
    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> UserAuthorityDict:
        return get_user_authority(request, *args, **kwargs)


class PlagsEndpointArgumentGetterFactory:
    __BUILDER_TABLE: Dict[
        Type[DjangoViewFuncArg], Type[AbsPlagsEndpointArgumentGetter]
    ] = {
        str: PlagsEndpointStrArgumentGetter,
        int: PlagsEndpointIntArgumentGetter,
        HttpRequest: PlagsEndpointHttpRequestArgumentGetter,
        User: PlagsEndpointUserArgumentGetter,
        Organization: PlagsEndpointOrganizationArgumentGetter,
        _Optional_Organization: PlagsEndpointOptionalOrganizationArgumentGetter,
        Course: PlagsEndpointCourseArgumentGetter,
        _Optional_Course: PlagsEndpointOptionalCourseArgumentGetter,
        Exercise: PlagsEndpointExerciseArgumentGetter,
        Submission: PlagsEndpointSubmissionArgumentGetter,
        SubmissionParcel: PlagsEndpointSubmissionParcelArgumentGetter,
        CustomEvaluationTag: PlagsEndpointCustomEvaluationTagArgumentGetter,
        CourseTopNoticeByOrganization: PlagsEndpointCourseTopNoticeByOrganizationArgumentGetter,
        # NOTE これ pylint のバグだと思う、型とそのインスタンスは別物
        UserAuthorityDict: PlagsEndpointUserAuthorityDictArgumentGetter,  # pylint:disable=unhashable-member
    }

    @classmethod
    def build(cls, parameter: EndpointParameter) -> AbsPlagsEndpointArgumentGetter:
        if parameter.type not in cls.__BUILDER_TABLE:
            raise SystemLogicalError(f"unexpected {parameter.type=!r}")
        return cls.__BUILDER_TABLE[parameter.type](parameter)

    @classmethod
    def assert_fully_defined(cls) -> None:
        "定義されているべきものが定義されていることを確認"
        duty = set(get_args(DjangoViewFuncArg))
        defined = set(cls.__BUILDER_TABLE)
        assert duty == defined, (duty - defined, defined - duty)


PlagsEndpointArgumentGetterFactory.assert_fully_defined()


class PlagsEndpointCaller:
    def __init__(
        self,
        view_func: DjangoViewFunc,
        arg_builders: Tuple[AbsPlagsEndpointArgumentGetter, ...],
    ) -> None:
        self._view_func = view_func
        self._arg_builders = arg_builders

    def __call__(
        self,
        request: HttpRequest,
        *args: DjangoRequestArg,
        **kwargs: DjangoRequestKwarg,
    ) -> HttpResponse:
        view_args: Tuple[DjangoViewFuncArg, ...] = tuple(
            arg_builder(request, *args, **kwargs) for arg_builder in self._arg_builders
        )
        return self._view_func(*view_args)


class PlagsDjangoViewEndpointBuilder:
    @staticmethod
    def build(view_func: DjangoViewFunc) -> _TDjangoViewEndpointFunc:
        if not hasattr(view_func, "__view_endpoint_annotations__"):
            raise SystemLogicalError(
                "__view_endpoint_annotations__ property is missing, "
                "possibly forget to decorate with `annotate_view_endpoint` ?"
            )
        view_endpoint_annotations_maybe: Any = view_func.__view_endpoint_annotations__
        if not isinstance(view_endpoint_annotations_maybe, ViewEndpointAnnotationData):
            raise SystemLogicalError(
                "__view_endpoint_annotations__ property must be of type ViewEndpointAnnotationData, "
                f"got {type(view_endpoint_annotations_maybe)!r}"
            )
        view_endpoint_annotations: ViewEndpointAnnotationData = (
            view_endpoint_annotations_maybe
        )

        arg_builders: Tuple[AbsPlagsEndpointArgumentGetter, ...] = tuple(
            PlagsEndpointArgumentGetterFactory.build(parameter)
            for parameter in view_endpoint_annotations.require_parameters
        )
        decorated_func = PlagsEndpointCaller(view_func, arg_builders)

        # ATTENTION デコレータはコード上での記述順序の逆順で呼び出されることに注意

        if view_endpoint_annotations.require_capabilities:
            decorated_func = check_user_authority_without_args(
                view_endpoint_annotations.require_capabilities,
                require_active_account=view_endpoint_annotations.require_active_account,
            )(decorated_func)
        elif view_endpoint_annotations.require_active_account:
            decorated_func = check_user_authority_without_args(
                UserAuthorityCapabilityKeys.IS_ACTIVE, require_active_account=False
            )(decorated_func)

        decorated_func = check_and_notify_exception(decorated_func)

        if view_endpoint_annotations.require_login:
            decorated_func = login_required(decorated_func)

        if (
            threshold := view_endpoint_annotations.profile_save_elapse_threshold
        ) is not None:
            decorated_func = with_profile(save_elapse_threshold=threshold)(
                decorated_func
            )

        return decorated_func


class AbsPlagsView(View):
    __AVAILABLE_METHOD_NAMES__: Tuple[str, ...] = ("_get", "_post")

    def __init__(self, **kwargs: Any) -> None:
        for method_name in self.__AVAILABLE_METHOD_NAMES__:
            if not hasattr(self, method_name):
                continue
            plags_implementation: DjangoViewFunc = getattr(self, method_name)

            setattr(
                self,
                method_name.lstrip("_"),
                PlagsDjangoViewEndpointBuilder.build(plags_implementation),
            )
        super().__init__(**kwargs)
