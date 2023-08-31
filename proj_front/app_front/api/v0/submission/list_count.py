import math

from django.contrib.auth.decorators import login_required
from django.http import Http404
from pydantic import BaseModel

from app_front.core.api_decorator import api_post
from app_front.core.exercise import get_shared_after_confirmed_exercise_names
from app_front.core.submission_filter import (
    SubmissionFilterQueryQueryBuilder,
    SubmissionFilterQueryQueryBuilderInputContext,
    SubmissionFilterQueryQueryExecutor,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.utils.auth_util import (
    RequestContext,
    annex_context,
    check_and_notify_api_exception,
)
from app_front.utils.exception_util import ExceptionHandler, UserResponsibleException


class RequestData(BaseModel):
    query: str


class ResponseData(BaseModel):
    count: int


LOCATION = ["submission.list_count"]


@login_required
@annex_context
@check_and_notify_api_exception
@api_post(RequestData)
def api_submission_list_count(
    context: RequestContext, data: RequestData
) -> ResponseData:
    if not context.user_authority.can_confirm_submission:
        raise Http404

    input_context = SubmissionFilterQueryQueryBuilderInputContext(
        organization=context.organization,
        course=context.course,
        request_user=context.request.user,
        is_reviewer=context.user_authority.can_confirm_submission,
        # MAYBE Course/Exercise 設定を読むべきかもしれない
        has_perfect_score_visible_authority=context.user_authority_on_course.is_as_lecturer(),
        has_perfect_remarks_visible_authority=context.user_authority_on_course.is_as_lecturer(),
        force_disable_too_many_rows_protection=True,  # Exportなので全件出す
        cache_shared_after_confirmed_exercise_names=get_shared_after_confirmed_exercise_names(
            context.course
        ),
    )
    with ExceptionHandler("Process Submission Filter", context.request):
        (
            output_context,
            query_data,
        ) = SubmissionFilterQueryQueryBuilder.validate_query_string(
            input_context, data.query
        )

    if not output_context.is_valid_with_guard_query_data(query_data):
        raise UserResponsibleException(
            "Invalid query", output_context=output_context, query_data=query_data
        )

    result = SubmissionFilterQueryQueryExecutor.get_submission_evaluations(
        input_context, output_context, query_data
    )
    submissions = result.submission_evaluations
    elapse_seconds = (
        "N/A" if math.isnan(result.elapse_seconds) else f"{result.elapse_seconds:.03f}"
    )

    if elapse_seconds != "N/A" and result.elapse_seconds >= 5.0:
        SLACK_NOTIFIER.warning(
            "SubmissionFilterExecutor: Slow query found: "
            + context.request.build_absolute_uri()
        )

    return ResponseData(count=len(submissions))
