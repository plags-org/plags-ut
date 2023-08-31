from typing import List, Set

from django.contrib.auth.decorators import login_required
from django.db import transaction
from pydantic.main import BaseModel

from app_front.core.api_decorator import api_post
from app_front.core.submission import (
    SpecialValueEnum,
    SubmissionConfirmData,
    confirm_submission,
)
from app_front.core.utils import block_split_range
from app_front.models import Submission
from app_front.utils.auth_util import (
    RequestContext,
    annex_context,
    check_and_notify_api_exception,
    check_context_user_authority,
)


class RequestData(BaseModel):
    submission_ids: List[int]


class ResponseData(BaseModel):
    num_updated: int
    num_untouched: int


# NOTE sqlite3 3.22 では、最大 999 個までしか変数を指定できない (SQLITE_MAX_VARIABLE_NUMBER)
#      大きくしすぎると (更新フィールド数 × 行数) sqlite3.OperationalError: too many SQL variables を食らう
#      現状の confirm_submission は最大10フィールドを更新するので、一旦50件を上限とした（一応90でも動いていそうだったが）
# NOTE sqlite3 3.32 以降では 9999 から 32766 まで増えるようだ
MAX_SUBMISSIONS_FOR_BULK_CONFIRM = 50


@login_required
@annex_context
@check_and_notify_api_exception
@check_context_user_authority("can_confirm_submission")
@api_post(RequestData)
def api_submission_bulk_confirm(
    context: RequestContext, data: RequestData
) -> ResponseData:
    num_updated = 0
    num_untouched = 0
    for block_start, block_end in block_split_range(
        len(data.submission_ids), MAX_SUBMISSIONS_FOR_BULK_CONFIRM
    ):
        print(f"submission_bulk_confirm: Block [{block_start}:{block_end}] in progress")
        result = _bulk_confirm_impl(context, data.submission_ids[block_start:block_end])
        num_updated += result.num_updated
        num_untouched += result.num_untouched
    return ResponseData(
        num_updated=num_updated,
        num_untouched=num_untouched,
    )


def _bulk_confirm_impl(
    context: RequestContext, submission_ids: List[int]
) -> ResponseData:
    num_untouched = 0
    assert (
        len(submission_ids) <= MAX_SUBMISSIONS_FOR_BULK_CONFIRM
    ), f"{len(submission_ids)} submissions specified at once (limit is {MAX_SUBMISSIONS_FOR_BULK_CONFIRM})"
    with transaction.atomic():
        updated_submissions = []
        overall_updated_fields: Set[str] = set()
        submissions = Submission.objects.filter(id__in=submission_ids).select_related(
            "organization", "course"
        )
        for submission in submissions:
            assert submission.organization.id == context.organization.id
            assert submission.course.id == context.course.id
            reviewer_remarks = submission.reviewer_remarks or ""
            reviewer_remarks += "\n\n" * bool(reviewer_remarks) + "(一括confirmによる更新)"
            confirm_data = SubmissionConfirmData(
                is_confirmed=True,
                review_grade=SpecialValueEnum.SKIP_UPDATE,
                review_comment=SpecialValueEnum.SKIP_UPDATE,
                reviewer_remarks=reviewer_remarks,
            )
            submission, _updated_items, updated_fields = confirm_submission(
                submission, context.request.user, confirm_data
            )
            if updated_fields:
                overall_updated_fields.update(updated_fields)
                updated_submissions.append(submission)
            else:
                num_untouched += 1
        if updated_submissions:
            Submission.objects.bulk_update(
                updated_submissions, tuple(overall_updated_fields)
            )
    return ResponseData(
        num_updated=len(updated_submissions),
        num_untouched=num_untouched,
    )
