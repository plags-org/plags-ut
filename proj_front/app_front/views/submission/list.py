import math
from typing import ClassVar, List

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.custom_evaluation_tag import (
    CustomEvaluationTagManager,
    get_custom_evaluation_tags_for_authority,
)
from app_front.core.exercise import get_shared_after_confirmed_exercise_names
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.submission import SubmissionEvaluationData
from app_front.core.submission_filter import (
    SubmissionFilterQueryQueryBuilder,
    SubmissionFilterQueryQueryBuilderInputContext,
    SubmissionFilterQueryQueryBuilderOutputContext,
    SubmissionFilterQueryQueryExecutor,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import Course, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.exception_util import ExceptionHandler


class ListSubmissionView(AbsPlagsView):
    TEMPLATE_FILE: ClassVar[str] = "submission/list.html"

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_LIST_SUBMISSION,)
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        input_context = SubmissionFilterQueryQueryBuilderInputContext(
            organization=organization,
            course=course,
            request_user=request_user,
            is_reviewer=user_authority["can_review_submission"],
            # MAYBE Course/Exercise 設定を読むべきかもしれない
            has_perfect_score_visible_authority=user_authority[
                "on_course"
            ].is_as_lecturer(),
            has_perfect_remarks_visible_authority=user_authority[
                "on_course"
            ].is_as_lecturer(),
            cache_shared_after_confirmed_exercise_names=get_shared_after_confirmed_exercise_names(
                course
            ),
        )
        output_context = SubmissionFilterQueryQueryBuilderOutputContext()
        with ExceptionHandler("Process Submission Filter", request):
            query_str = request.GET.get("q", "")
            (
                output_context,
                query_data,
            ) = SubmissionFilterQueryQueryBuilder.validate_query_string(
                input_context, query_str
            )

        submissions: List[SubmissionEvaluationData] = []
        is_limit_triggered = False
        is_too_many_rows_protection_triggered = False
        elapse_seconds: str = "N/A"

        if output_context.is_valid_with_guard_query_data(query_data):
            result = SubmissionFilterQueryQueryExecutor.get_submission_evaluations(
                input_context, output_context, query_data
            )
            submissions = result.submission_evaluations
            is_limit_triggered = result.is_limit_triggered
            is_too_many_rows_protection_triggered = (
                result.is_too_many_rows_protection_triggered
            )
            elapse_seconds = (
                "N/A"
                if math.isnan(result.elapse_seconds)
                else f"{result.elapse_seconds:.03f}"
            )

            if elapse_seconds != "N/A" and result.elapse_seconds >= 2.0:
                SLACK_NOTIFIER.warning(
                    "SubmissionFilterExecutor: Slow query found: "
                    + request.build_absolute_uri()
                )

        # NOTE あとに追加したものが上に来る
        for warning in reversed(output_context.warning_list):
            messages.warning(request, warning.to_message())
        for error in reversed(output_context.error_list):
            messages.error(request, error.to_message())

        submission_ids = [s.id for s in submissions]

        custom_evaluation_tags = get_custom_evaluation_tags_for_authority(
            organization, course, user_authority
        )
        custom_evaluation_tag_manager = CustomEvaluationTagManager(
            custom_evaluation_tags, user_authority
        )

        return render(
            request,
            cls.TEMPLATE_FILE,
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                submissions=submissions,
                submission_ids=submission_ids,
                custom_evaluation_tag_manager=custom_evaluation_tag_manager,
                is_limit_triggered=is_limit_triggered,
                is_too_many_rows_protection_triggered=is_too_many_rows_protection_triggered,
                elapse_seconds=elapse_seconds,
            ),
        )
