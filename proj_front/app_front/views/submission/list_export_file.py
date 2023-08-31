import math
import mimetypes
from typing import Iterable

from django.http.request import HttpRequest
from django.http.response import HttpResponse

from app_front.core.data_export import (
    convert_dataclasses_to_csv_str,
    iso8601_on_user_timezone,
)
from app_front.core.exercise import get_shared_after_confirmed_exercise_names
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.submission import ExportFormatSubmission, SubmissionEvaluationData
from app_front.core.submission_filter import (
    SubmissionFilterQueryQueryBuilder,
    SubmissionFilterQueryQueryBuilderInputContext,
    SubmissionFilterQueryQueryBuilderOutputContext,
    SubmissionFilterQueryQueryExecutor,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import Course, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.exception_util import ExceptionHandler, UserResponsibleException


class ListExportFileSubmissionView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_REVIEW_SUBMISSION,
        profile_save_elapse_threshold=5.0,
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
            force_disable_too_many_rows_protection=True,  # Exportなので全件出す
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

        if not output_context.is_valid_with_guard_query_data(query_data):
            raise UserResponsibleException(
                "Invalid query", output_context=output_context, query_data=query_data
            )

        result = SubmissionFilterQueryQueryExecutor.get_submission_evaluations(
            input_context, output_context, query_data
        )
        submissions = result.submission_evaluations
        elapse_seconds = (
            "N/A"
            if math.isnan(result.elapse_seconds)
            else f"{result.elapse_seconds:.03f}"
        )

        if elapse_seconds != "N/A" and result.elapse_seconds >= 5.0:
            SLACK_NOTIFIER.warning(
                "SubmissionFilterExecutor: Slow query found: "
                + request.build_absolute_uri()
            )

        user_timezone = request.user.timezone

        def convert_submission_evaluation_to_row(
            submission: SubmissionEvaluationData,
        ) -> ExportFormatSubmission:
            return ExportFormatSubmission(
                exercise=submission.exercise__name,
                submitted_by=submission.submitted_by__username,
                submitted_at=iso8601_on_user_timezone(
                    submission.submitted_at, user_timezone
                ),
                delayed=submission.is_delayed_submission,
                confirmed=submission.is_lecturer_evaluation_confirmed,
                remarks=submission.reviewer_remarks,
                score=submission.lecturer_grade,
                comment=submission.lecturer_comment,
                system_score=submission.overall_grade,
            )

        def data_gen() -> Iterable[ExportFormatSubmission]:
            for submission in submissions:
                yield convert_submission_evaluation_to_row(submission)

        file_content = convert_dataclasses_to_csv_str(
            ExportFormatSubmission, data_gen()
        )


        file_name = (
            f"export_submissions_filtered__{organization.name}__{course.name}.csv"
        )
        response = HttpResponse(
            content_type=mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )
        response["Content-Disposition"] = f'attachment; filename="{file_name}"'
        response.write(file_content)

        return response
