from typing import Dict

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.custom_evaluation_tag import (
    CustomEvaluationTagManager,
    get_custom_evaluation_tags_for_authority,
)
from app_front.core.exercise import get_visible_exercises
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.submission import get_user_submissions
from app_front.core.types import ExerciseName
from app_front.models import Course, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class SubmissionDashboardView(AbsPlagsView):
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
        custom_evaluation_tags = get_custom_evaluation_tags_for_authority(
            organization, course, user_authority
        )
        custom_evaluation_tag_manager = CustomEvaluationTagManager(
            custom_evaluation_tags, user_authority
        )

        exercise_submissions: Dict[ExerciseName, dict] = {}
        for exercise in get_visible_exercises(user_authority, course):
            exercise_submissions[exercise.name] = dict(
                exercise=exercise,
                # NOTE 最新提出とレビュー済み提出を残す
                submissions=[
                    submission
                    for idx, submission in enumerate(
                        get_user_submissions(request.user, course, exercise)
                    )
                    if idx == 0 or submission.is_lecturer_evaluation_confirmed
                ],
            )

        return render(
            request,
            "submission/dashboard.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                exercise_submissions=exercise_submissions,
                custom_evaluation_tag_manager=custom_evaluation_tag_manager,
            ),
        )
