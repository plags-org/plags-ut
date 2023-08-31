from django.contrib.auth.decorators import login_required
from pydantic import BaseModel

from app_front.core.api_decorator import ApiErrorData, ApiException, api_post
from app_front.core.submission import is_submission_visible_to_user
from app_front.core.submission_parcel import workaround_supply_default_file_name
from app_front.models import Submission
from app_front.utils.auth_util import (
    RequestContext,
    annex_context,
    check_and_notify_api_exception,
)


class RequestData(BaseModel):
    id: int


class UserData(BaseModel):
    id: int
    username: str


class FileData(BaseModel):
    name: str
    content: str


class ResponseData(BaseModel):
    submission_file: FileData


LOCATION = ["submission.get"]


@login_required
@annex_context
@check_and_notify_api_exception
@api_post(RequestData)
def api_submission_get(context: RequestContext, data: RequestData) -> ResponseData:
    return submission_get(context, data)


def submission_get(context: RequestContext, data: RequestData) -> ResponseData:
    # NOTE 可視性の定義:
    #                             | 行レベル       | 列レベル
    # UserAuthorityEnum.READONLY  | 自分の提出のみ | TA・教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.ANONYMOUS | 自分の提出のみ | TA・教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.STUDENT   | 自分の提出のみ | TA・教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.ASSISTANT | 全員の提出     | 教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.LECTURER  | 全員の提出     | 全て可視
    # UserAuthorityEnum.MANAGER   | 全員の提出     | 全て可視
    try:
        submission: Submission = Submission.objects.get(id=data.id)
        # 行レベル可視性処理: 学生より上（TA以上）でなければ自分の提出しか見えない
        is_reviewer = context.user_authority.can_review_submission
        if not is_submission_visible_to_user(
            submission, context.request.user, is_reviewer
        ):
            raise ApiException(
                ApiErrorData(
                    loc=LOCATION,
                    msg="No view authority on specified Submission",
                    type="Submission.NoViewAuthority",
                )
            )
        return ResponseData(
            submission_file=FileData(
                name=workaround_supply_default_file_name(None),
                content=submission.submission_file.read(),
            ),
        )
    except Submission.DoesNotExist as exc:
        raise ApiException(
            ApiErrorData(
                loc=LOCATION,
                msg="Specified Submission does not exist",
                type="Submission.DoesNotExist",
            )
        ) from exc
