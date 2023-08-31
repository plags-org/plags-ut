from typing import List, Tuple

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.custom_evaluation_tag import (
    CustomEvaluationTagManager,
    get_custom_evaluation_tags_for_authority,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.submission import ReviewSubmissionAuthorityParams
from app_front.forms import ReviewSubmissionForm
from app_front.models import Course, Organization, Submission
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.exception_util import ExceptionHandler, UserResponsibleException


class BulkReviewSubmissionView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_REVIEW_SUBMISSION
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        submissions: List[Submission] = []

        with ExceptionHandler("Generate Bulk Review Page", request):
            if "ids" not in request.GET:
                raise UserResponsibleException('Required parameter is missing: "ids"')
            if not request.GET["ids"]:
                raise UserResponsibleException('Required parameter is empty: "ids"')

            submission_ids = list(map(int, request.GET["ids"].split(",")))
            if len(submission_ids) > 50:
                raise UserResponsibleException(
                    f"Too many submissions specified ({len(submission_ids)} > 50)"
                )

            submissions = list(
                Submission.objects.filter(id__in=submission_ids).select_related(
                    "exercise",
                    "submitted_by",
                    "confirmed_by",
                    "reviewer_remarks_updated_by",
                    "lecturer_comment_updated_by",
                )
            )
            assert len(submission_ids) == len(
                submissions
            ), "Invalid submission id in ids"

        custom_evaluation_tags = get_custom_evaluation_tags_for_authority(
            organization, course, user_authority
        )
        custom_evaluation_tag_manager = CustomEvaluationTagManager(
            custom_evaluation_tags, user_authority
        )

        submission_id_list: List[int] = [submission.id for submission in submissions]
        submission_review_forms: List[Tuple[Submission, ReviewSubmissionForm]] = [
            (
                submission,
                ReviewSubmissionForm(
                    authority_params=ReviewSubmissionAuthorityParams.make_from_auth_dict(
                        user_authority, submission
                    ),
                    initial_submission=submission,
                    # ATTENTION updateSubmissionReviewPreview は JavaScript で定義されたclient-sideの関数
                    dom_event_oninput=f"updateSubmissionReviewPreview({submission.id})",
                    # ATTENTION このID命名規則は client-side JavaScript 側で getElementById に利用される
                    auto_id="id_%s__for_submission_" + str(submission.id),
                ),
            )
            for submission in submissions
        ]

        return render(
            request,
            "submission/bulk_review.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                custom_evaluation_tag_manager=custom_evaluation_tag_manager,
                submissions=submissions,
                submission_id_list=submission_id_list,
                submission_review_forms=submission_review_forms,
                is_reviewer=True,
            ),
        )
