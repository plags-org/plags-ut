import datetime
import io
import json
import zipfile
from typing import Any, List, Optional, Union

from django.core.files.base import ContentFile
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from pydantic.main import BaseModel

from app_front.core.judge_util import fetch_evaluation_result_if_necessary
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.types import ExerciseName, UserName
from app_front.models import (
    Course,
    CourseAsyncJob,
    Exercise,
    Organization,
    Submission,
    SubmissionTypeEnum,
)
from app_front.utils.auth_util import UserAuthorityCapabilityKeys
from app_front.utils.parameter_decoder import encode_submission_id
from app_front.utils.time_util import get_current_datetime


class SubmissionFullExportRowModel(BaseModel):
    id: int
    permalink: str
    exercise_name: ExerciseName
    exercise_version: str
    submitted_at: datetime.datetime
    submitted_by: UserName
    submission_file: Union[str, dict]
    rejudge_original_submission_id: Optional[int]
    rejudge_deep_original_submission_id: Optional[int]
    rejudge_requested_at: Optional[datetime.datetime]
    rejudge_requested_by: Optional[UserName]
    is_latest_submission: bool
    is_lecturer_evaluation_confirmed: bool
    confirmed_at: Optional[datetime.datetime]
    confirmed_by: Optional[UserName]
    lecturer_grade: Optional[int]
    lecturer_comment: str
    lecturer_comment_updated_at: Optional[datetime.datetime]
    lecturer_comment_updated_by: Optional[UserName]
    reviewer_remarks: str
    reviewer_remarks_updated_at: Optional[datetime.datetime]
    reviewer_remarks_updated_by: Optional[UserName]
    external_submission_id: Optional[int]
    evaluated_at: Optional[datetime.datetime]
    evaluation_result_json: Optional[dict]
    overall_grade: Optional[int]
    overall_status: Optional[str]
    observed_statuses: Optional[List[Union[str, dict]]]

    @staticmethod
    def from_submission(
        submission: Submission,
        *,
        request: HttpRequest,
        organization: Organization,
        course: Course,
    ) -> "SubmissionFullExportRowModel":
        with submission.submission_file.open("r") as f:
            submission_file_content_str: str = f.read()
            submission_file_content: Union[str, dict] = submission_file_content_str
            # As-isの場合はnotebook形式なので辞書形式で応答する
            if not submission.is_autograded_exercise:
                submission_file_content = json.loads(submission_file_content_str)

        def to_permalink(submission: Submission) -> str:
            s_eb64 = encode_submission_id(course, submission.id)
            path = f"/view/o/{organization.name}/c/{course.name}/s/{s_eb64}/submission/"
            return f"{request.scheme}://{request.get_host()}{path}"

        def json_load_optional(json_str: Optional[str]) -> Optional[Any]:
            if json_str is None:
                return None
            return json.loads(json_str)

        return SubmissionFullExportRowModel(
            id=submission.id,
            permalink=to_permalink(submission),
            exercise_name=submission.exercise.name,
            exercise_version=submission.exercise_version,
            submitted_at=submission.submitted_at,
            submitted_by=submission.submitted_by.username,
            submission_file=submission_file_content,
            rejudge_original_submission_id=(
                ros := submission.rejudge_original_submission
            )
            and ros.id,
            rejudge_deep_original_submission_id=(
                rods := submission.rejudge_deep_original_submission
            )
            and rods.id,
            rejudge_requested_at=submission.rejudge_requested_at,
            rejudge_requested_by=(rrb := submission.rejudge_requested_by)
            and rrb.username,
            is_latest_submission=submission.is_latest_submission,
            is_lecturer_evaluation_confirmed=submission.is_lecturer_evaluation_confirmed,
            confirmed_at=submission.confirmed_at,
            confirmed_by=(cb := submission.confirmed_by) and cb.username,
            lecturer_grade=submission.lecturer_grade,
            lecturer_comment=submission.lecturer_comment,
            lecturer_comment_updated_at=submission.lecturer_comment_updated_at,
            lecturer_comment_updated_by=(lcub := submission.lecturer_comment_updated_by)
            and lcub.username,
            reviewer_remarks=submission.reviewer_remarks,
            reviewer_remarks_updated_at=submission.reviewer_remarks_updated_at,
            reviewer_remarks_updated_by=(rrub := submission.reviewer_remarks_updated_by)
            and rrub.username,
            external_submission_id=submission.external_submission_id,
            evaluated_at=submission.evaluated_at,
            evaluation_result_json=json_load_optional(
                submission.evaluation_result_json
            ),
            overall_grade=submission.overall_grade,
            overall_status=submission.overall_status,
            observed_statuses=json_load_optional(submission.observed_statuses),
        )


class SubmissionFullExportModel(BaseModel):
    submission_list: List[SubmissionFullExportRowModel]


class SubmissionFullExportView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_REVIEW_SUBMISSION,
        profile_save_elapse_threshold=5.0,
    )
    def _get(
        cls,
        request: HttpRequest,
        organization: Organization,
        course: Course,
        exercise: Exercise,
    ) -> HttpResponse:
        job_started_at = get_current_datetime()
        job: CourseAsyncJob = CourseAsyncJob.objects.create(
            organization=organization,
            course=course,
            executed_by=request.user,
            job_type="submission/full_export",
            job_options=json.dumps(dict(exercise_name=exercise.name)),
            job_started_at=job_started_at,
            job_status=CourseAsyncJob.JobStatus.ONGOING,
            job_outcome_type=CourseAsyncJob.JobOutcomeType.FILE,
        )

        submission_filter = dict(
            organization=organization,
            course=course,
            exercise=exercise,
            submission_type=SubmissionTypeEnum.NORMAL,
        )

        # prefetch
        for submission in Submission.objects.filter(**submission_filter):
            fetch_evaluation_result_if_necessary(submission, force=True)

        submissions = Submission.objects.filter(**submission_filter).select_related(
            "exercise__course",  # for is_submission_delayed
            "exercise",
            "submitted_by",
            "rejudge_requested_by",
            "confirmed_by",
            "lecturer_comment_updated_by",
            "reviewer_remarks_updated_by",
        )

        file_content = SubmissionFullExportModel(
            submission_list=[
                SubmissionFullExportRowModel.from_submission(
                    s, request=request, organization=organization, course=course
                )
                for s in submissions
            ]
        )

        file_name = f"full_export_submissions__{organization.name}__{course.name}__{exercise.name}.json"
        zip_file_name = file_name + ".zip"

        zip_stream = io.BytesIO()
        with zipfile.ZipFile(
            zip_stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=5
        ) as f_zip:
            f_zip.writestr(file_name, file_content.json(ensure_ascii=False))

        job.job_finished_at = get_current_datetime()
        job.job_status = CourseAsyncJob.JobStatus.SUCCEEDED
        job.job_outcome_file = ContentFile(zip_stream.getvalue(), zip_file_name)
        job.job_outcome_filename = zip_file_name
        job.save()

        response = HttpResponse(content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{zip_file_name}"'
        response.write(zip_stream.getvalue())
        # response.write(file_content.json(ensure_ascii=False))

        return response
