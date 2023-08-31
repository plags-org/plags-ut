from django.http.request import HttpRequest
from django.http.response import Http404, HttpResponse
from django.shortcuts import render

from app_front.core.custom_evaluation_tag import (
    CustomEvaluationTagManager,
    get_custom_evaluation_tags_for_authority,
)
from app_front.core.judge_util import fetch_evaluation_result_if_necessary
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.submission import SubmissionEvaluationData
from app_front.models import Course, Organization, Submission, SubmissionParcel
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class SubmissionParcelView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_LIST_SUBMISSION
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        submission_parcel: SubmissionParcel,
    ) -> HttpResponse:
        custom_evaluation_tags = get_custom_evaluation_tags_for_authority(
            organization, course, user_authority
        )
        custom_evaluation_tag_manager = CustomEvaluationTagManager(
            custom_evaluation_tags, user_authority
        )

        is_reviewer = user_authority["can_review_submission"]
        if not is_reviewer:
            # この人は自分の提出しか確認できないべき
            if submission_parcel.submitted_by != request.user:
                # NOTE 遅延時間の違いにより「提出が存在する」ことは露呈してしまう恐れがある
                raise Http404()

        submissions_query = Submission.objects.filter(
            submission_parcel=submission_parcel
        ).order_by("exercise__name")
        for submission in submissions_query:
            fetch_evaluation_result_if_necessary(submission, force=is_reviewer)

        submissions = list(
            map(SubmissionEvaluationData.from_submission, submissions_query)
        )

        return render(
            request,
            "submission_parcel/view.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                submission_parcel=submission_parcel,
                submissions=submissions,
                custom_evaluation_tag_manager=custom_evaluation_tag_manager,
            ),
        )
