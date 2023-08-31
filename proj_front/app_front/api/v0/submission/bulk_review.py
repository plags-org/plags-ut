from collections import Counter
from typing import List, Set

from django.contrib.auth.decorators import login_required
from django.db import transaction
from pydantic.main import BaseModel

from app_front.core.api_decorator import api_post
from app_front.core.submission import (
    ReviewSubmissionAuthorityParams,
    SubmissionConfirmData,
    SubmissionReviewData,
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
    submission_reviews: List[SubmissionReviewData]


class ResponseData(BaseModel):
    num_updated: int
    num_untouched: int


# NOTE sqlite3 3.22 では、最大 999 個までしか変数を指定できない (SQLITE_MAX_VARIABLE_NUMBER)
#      大きくしすぎると (更新フィールド数 × 行数) sqlite3.OperationalError: too many SQL variables を食らう
#      現状の confirm_submission は最大13フィールドを更新するので、一旦50件を上限とした
#      （一応900フィールドでも動いていそうなことは確認した）
# NOTE sqlite3 3.32 以降では 9999 から 32766 まで増えるようだ
MAX_SUBMISSIONS_FOR_BULK_REVIEW = 50


@login_required
@annex_context
@check_and_notify_api_exception
@check_context_user_authority("can_review_submission")
@api_post(RequestData)
def api_submission_bulk_review(
    context: RequestContext, data: RequestData
) -> ResponseData:
    num_updated = 0
    num_untouched = 0
    for block_start, block_end in block_split_range(
        len(data.submission_reviews), MAX_SUBMISSIONS_FOR_BULK_REVIEW
    ):
        print(f"submission_bulk_review: Block [{block_start}:{block_end}] in progress")
        result = _bulk_review_impl(
            context, data.submission_reviews[block_start:block_end]
        )
        num_updated += result.num_updated
        num_untouched += result.num_untouched
    return ResponseData(
        num_updated=num_updated,
        num_untouched=num_untouched,
    )


def _bulk_review_impl(
    context: RequestContext, submission_reviews: List[SubmissionReviewData]
) -> ResponseData:
    num_untouched = 0
    assert (
        len(submission_reviews) <= MAX_SUBMISSIONS_FOR_BULK_REVIEW
    ), f"{len(submission_reviews)} submissions specified at once (limit is {MAX_SUBMISSIONS_FOR_BULK_REVIEW})"
    submission_id_to_review = {review.id: review for review in submission_reviews}
    assert len(submission_id_to_review) == len(
        submission_reviews
    ), f"Specified reviews have duplicated ids: {Counter(review.id for review in submission_reviews).most_common()}"

    submission_ids = list(submission_id_to_review)

    with transaction.atomic():
        updated_submissions = []
        overall_updated_fields: Set[str] = set()
        submissions = Submission.objects.filter(id__in=submission_ids).select_related(
            "organization", "course"
        )
        for submission in submissions:
            assert submission.organization.id == context.organization.id
            assert submission.course.id == context.course.id
            assert (
                submission.id in submission_id_to_review
            ), f"Unexpected submission id: {submission.id}"
            review_data = SubmissionConfirmData.from_review_data(
                submission_id_to_review[submission.id],
                authority_params=ReviewSubmissionAuthorityParams.make_from_context(
                    context, submission
                ),
            )
            submission, _updated_items, updated_fields = confirm_submission(
                submission, context.request.user, review_data
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
