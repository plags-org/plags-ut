from typing import Optional

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.http.response import Http404
from django.shortcuts import redirect, render

from app_front.core.custom_evaluation_tag import (
    CustomEvaluationTagManager,
    get_custom_evaluation_tags_for_authority,
)
from app_front.core.judge_util import fetch_evaluation_result_if_necessary
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.submission import (
    ReviewSubmissionAuthorityParams,
    SubmissionConfirmData,
    SubmissionEvaluationData,
    SubmissionReviewData,
    confirm_submission,
    is_submission_visible_to_user,
    rejudge_submission,
)
from app_front.forms import ReviewSubmissionForm
from app_front.models import Course, Exercise, Organization, Submission
from app_front.utils.auth_util import (
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
    check_user_capability,
)
from app_front.utils.parameter_decoder import encode_submission_id, get_exercise_info


class ViewSubmissionView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        submission: Submission,
        *,
        review_form: Optional[ReviewSubmissionForm] = None,
    ) -> HttpResponse:
        is_reviewer = user_authority["can_review_submission"]
        request_user = get_request_user_safe(request)
        if not is_submission_visible_to_user(submission, request_user, is_reviewer):
            # NOTE 遅延時間の違いにより「提出が存在する」ことは露呈してしまう恐れがある
            raise Http404()

        fetch_evaluation_result_if_necessary(submission, force=is_reviewer)

        custom_evaluation_tags = get_custom_evaluation_tags_for_authority(
            organization, course, user_authority
        )
        custom_evaluation_tag_manager = CustomEvaluationTagManager(
            custom_evaluation_tags, user_authority
        )

        submission_exercise: Exercise = submission.exercise
        exercise_info = get_exercise_info(organization, submission_exercise)

        # 少なくともそれが「最新であるか」は確認したそう

        is_confirmable = user_authority.get("can_confirm_submission")

        # レビュワーにのみレビューフォームを提供する
        if is_reviewer:
            if review_form is None:
                review_form = ReviewSubmissionForm(
                    authority_params=ReviewSubmissionAuthorityParams.make_from_auth_dict(
                        user_authority, submission
                    ),
                    initial_submission=submission,
                )

        return render(
            request,
            "submission/view.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                exercise_info=exercise_info,
                submission_parcel=submission.submission_parcel,
                submission=submission,
                submissions=[SubmissionEvaluationData.from_submission(submission)],
                review_form=review_form,
                is_reviewer=is_reviewer,
                is_confirmable=is_confirmable,
                custom_evaluation_tag_manager=custom_evaluation_tag_manager,
            ),
        )

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
        submission: Submission,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization, course, submission)

    @classmethod
    def _post_confirm(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        submission: Submission,
    ) -> HttpResponse:
        # 提出物のレビュー権限がなければ弾く
        if not check_user_capability(
            user_authority, UserAuthorityCapabilityKeys.CAN_REVIEW_SUBMISSION
        ):
            messages.error(request, "You have no review authority on submission.")
            return cls._view(request, user_authority, organization, course, submission)

        request_user = get_request_user_safe(request)

        authority_params = ReviewSubmissionAuthorityParams.make_from_auth_dict(
            user_authority, submission
        )
        review_form = ReviewSubmissionForm(
            request.POST,
            authority_params=authority_params,
        )
        if not review_form.is_valid():
            return cls._view(
                request,
                user_authority,
                organization,
                course,
                submission,
                review_form=review_form,
            )

        data_dict = dict(**review_form.cleaned_data, id=submission.id)
        data = SubmissionConfirmData.from_review_data(
            SubmissionReviewData.parse_obj(data_dict),
            authority_params=authority_params,
        )
        submission, updated_items, _updated_fields = confirm_submission(
            submission, request_user, data
        )

        if updated_items:
            submission.save()
            messages.success(request, f'Updated: {", ".join(updated_items)}')
        else:
            messages.info(request, "No update performed: no change detected")

        s_eb64 = encode_submission_id(course, submission.id)
        return redirect(
            "submission/view",
            o_name=organization.name,
            c_name=course.name,
            s_eb64=s_eb64,
        )

    @classmethod
    def _post_rejudge(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        submission: Submission,
    ) -> HttpResponse:
        # 提出物の再評価権限がなければ弾く
        if not check_user_capability(
            user_authority, UserAuthorityCapabilityKeys.CAN_REJUDGE_SUBMISSION
        ):
            messages.error(request, "You have no rejudge authority on submission.")
            return cls._view(request, user_authority, organization, course, submission)

        request_user = get_request_user_safe(request)

        rejudged_submission = rejudge_submission(submission, request_user)

        s_eb64 = encode_submission_id(course, rejudged_submission.id)
        return redirect(
            "submission/view",
            o_name=organization.name,
            c_name=course.name,
            s_eb64=s_eb64,
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_LIST_SUBMISSION
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        submission: Submission,
    ) -> HttpResponse:
        if "confirm" in request.POST:
            return cls._post_confirm(
                request, user_authority, organization, course, submission
            )
        if "rejudge" in request.POST:
            return cls._post_rejudge(
                request, user_authority, organization, course, submission
            )
        return cls._view(request, user_authority, organization, course, submission)
