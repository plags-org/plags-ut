from collections import defaultdict
from typing import DefaultDict, List, Type

from django.contrib.auth.decorators import login_required
from django.db import transaction
from pydantic import BaseModel

from app_front.core.api_decorator import api_post
from app_front.core.submission import RejudgeException, rejudge_submission
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
    num_rejudged: int
    num_error: int
    rejudge_errors: List[str]


@login_required
@annex_context
@check_and_notify_api_exception
@check_context_user_authority("can_create_exercise")
@api_post(RequestData)
def api_submission_bulk_rejudge(
    context: RequestContext, data: RequestData
) -> ResponseData:
    assert context.organization is not None
    assert context.course is not None

    num_rejudged: int = 0
    rejudge_type_id_list: DefaultDict[Type[Exception], List[int]] = defaultdict(list)
    num_error = 0
    with transaction.atomic():
        submissions = Submission.objects.filter(
            id__in=data.submission_ids
        ).select_related("organization", "course")
        for submission in submissions:
            assert submission.organization.id == context.organization.id
            assert submission.course.id == context.course.id
            try:
                rejudge_submission(submission, context.request.user)
            except RejudgeException as exc:
                num_error += 1
                rejudge_type_id_list[type(exc)].append(exc.submission_id)
    rejudge_errors: List[str] = [
        error_type.__name__ + ": " + ", ".join(map(str, id_list))
        for error_type, id_list in rejudge_type_id_list.items()
    ]
    return ResponseData(
        num_rejudged=num_rejudged,
        num_error=num_error,
        rejudge_errors=rejudge_errors,
    )
