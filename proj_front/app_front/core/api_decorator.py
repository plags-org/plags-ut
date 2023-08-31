import dataclasses
import functools
import json
import traceback
from typing import Final, List, Literal, Type, Union

from django.conf import settings
from django.http.response import Http404, JsonResponse
from pydantic.error_wrappers import ValidationError
from pydantic.main import BaseModel

from app_front.dependency.system_notification import SLACK_NOTIFIER


@dataclasses.dataclass
class ApiErrorData:
    loc: List[str]
    msg: str
    type: str


class ApiException(Exception):
    def __init__(self, api_error: Union[ApiErrorData, List[ApiErrorData]]) -> None:
        super().__init__()
        self.api_errors: List[ApiErrorData] = (
            api_error if isinstance(api_error, list) else [api_error]
        )


_INTERNAL_SERVER_ERROR: Final = ApiErrorData(
    loc=["__main__"],
    msg="Internal Server Error",
    type="InternalServerError",
)


def api_error_response(
    errors: List[ApiErrorData], *, status: int = 200
) -> JsonResponse:
    """
    APIエラー応答

    ステータスは200で返すのが標準で、やむを得ない事情がない限り変更すべきでない（フロント側でのエラーハンドルに影響する）
    """
    return JsonResponse(
        {
            "ok": False,
            "errors": [dataclasses.asdict(e) for e in errors],
        },
        status=status,
    )


def _api_wrap(request_model: Type[BaseModel], method: Literal["GET", "POST"]):
    def _wrapper(func):
        @functools.wraps(func)
        def _wrap(context):
            if context.request.method != method:
                return Http404

            try:
                obj = json.loads(context.request.body)
            except ValueError as exc:
                # NOTE いまのところはサーバーエラーとしているが、APIをフロント以外へ公開するようになるなら変えるべき
                SLACK_NOTIFIER.critical(f"ValueError\nAPI: {func.__name__}\n---\n{exc}")
                return api_error_response([_INTERNAL_SERVER_ERROR])

            try:
                request_data = request_model.parse_obj(obj)
            except ValidationError as exc:
                if settings.DEBUG:
                    SLACK_NOTIFIER.warning(
                        f"ValidationError\nAPI: {func.__name__}\n---\n{exc.json()!r}"
                    )
                print(exc.json())
                return JsonResponse({"ok": False, "errors": exc.json()}, status=400)

            try:
                response_data: BaseModel = func(context, request_data)
            except ApiException as exc:
                SLACK_NOTIFIER.critical(
                    f"API Error\nAPI: {func.__name__}",
                    tracebacks=traceback.format_exc(),
                )
                traceback.print_exc()
                return api_error_response(exc.api_errors)
            except Exception:  # pylint: disable=broad-except
                SLACK_NOTIFIER.critical(
                    f"Unexpected API Error\nAPI: {func.__name__}",
                    tracebacks=traceback.format_exc(),
                )
                traceback.print_exc()
                return api_error_response([_INTERNAL_SERVER_ERROR])

            return JsonResponse({"ok": True, "data": response_data.dict()})

        return _wrap

    return _wrapper


def api_get(request_model: Type[BaseModel]):
    return _api_wrap(request_model, method="GET")


def api_post(request_model: Type[BaseModel]):
    return _api_wrap(request_model, method="POST")
