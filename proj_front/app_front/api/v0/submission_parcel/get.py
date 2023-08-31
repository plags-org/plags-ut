from django.contrib.auth.decorators import login_required
from pydantic import BaseModel

from app_front.core.api_decorator import ApiErrorData, ApiException, api_post
from app_front.core.submission_parcel import workaround_supply_default_file_name
from app_front.models import SubmissionParcel
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
    submission_parcel_file: FileData


LOCATION = ["submission_parcel.get"]


@login_required
@annex_context
@check_and_notify_api_exception
@api_post(RequestData)
def api_submission_parcel_get(
    context: RequestContext, data: RequestData
) -> ResponseData:
    return submission_parcel_get(context, data)


def submission_parcel_get(context: RequestContext, data: RequestData) -> ResponseData:
    # NOTE 可視性の定義:
    #                             | 行レベル       | 列レベル
    # UserAuthorityEnum.READONLY  | 自分の提出のみ | TA・教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.ANONYMOUS | 自分の提出のみ | TA・教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.STUDENT   | 自分の提出のみ | TA・教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.ASSISTANT | 全員の提出     | 教員用は不可視、一部条件付き可視
    # UserAuthorityEnum.LECTURER  | 全員の提出     | 全て可視
    # UserAuthorityEnum.MANAGER   | 全員の提出     | 全て可視
    try:
        submission_parcel: SubmissionParcel = SubmissionParcel.objects.get(id=data.id)
        # 行レベル可視性処理: 学生より上（TA以上）でなければ自分の提出しか見えない
        if not context.user_authority_on_course.is_gt_student():
            if submission_parcel.submitted_by != context.request.user:
                raise ApiException(
                    ApiErrorData(
                        loc=LOCATION,
                        msg="No view authority on specified SubmissionParcel",
                        type="SubmissionParcel.NoViewAuthority",
                    )
                )
        return ResponseData(
            submission_parcel_file=FileData(
                name=workaround_supply_default_file_name(
                    submission_parcel.submission_parcel_file_initial_name
                ),
                content=submission_parcel.submission_parcel_file.read(),
            ),
        )
    except SubmissionParcel.DoesNotExist as exc:
        raise ApiException(
            ApiErrorData(
                loc=LOCATION,
                msg="Specified SubmissionParcel does not exist",
                type="SubmissionParcel.DoesNotExist",
            )
        ) from exc
