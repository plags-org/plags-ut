import traceback
from typing import Final, Optional

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.exercise import is_trial_on_exercise_allowed
from app_front.core.form_types import ExerciseConcreteIdentity
from app_front.core.judge_util import insert_trial_submission, send_submission_to_judger
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import SubmitEditorForm
from app_front.models import (
    Course,
    Exercise,
    Organization,
    Submission,
    SubmissionTypeEnum,
)
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.parameter_decoder import encode_submission_id, get_exercise_info

_MAX_SIMULTANEOUS_TRIAL_EVALUATIONS: Final = 4


class ExerciseViewView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        exercise: Exercise,
        *,
        submit_editor_form: Optional[SubmitEditorForm] = None,
    ) -> HttpResponse:
        exercise_info = get_exercise_info(organization, exercise)
        return render(
            request,
            "exercise/view.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                exercise=exercise,
                exercise_info=exercise_info,
                submit_editor_form=submit_editor_form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(
            UserAuthorityCapabilityKeys.CAN_VIEW_EXERCISE,
            UserAuthorityCapabilityKeys.CAN_VIEW_EXERCISE_PUBLISHED,
        )
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        exercise: Exercise,
    ) -> HttpResponse:
        submit_editor_form: Optional[SubmitEditorForm] = None
        if is_trial_on_exercise_allowed(exercise, user_authority):
            editor_textarea_attrs = {
                "id": f"id_view_exercise_concrete_editor__{exercise.name}",
                "class": " ".join(("view_exercise_editor",)),
                "rows": 0,
                "cols": 0,
            }
            exercise_concrete_identity = ExerciseConcreteIdentity(
                name=exercise.name,
                version=exercise.latest_version,
                concrete_hash=exercise.latest_concrete_hash,
            )
            submit_editor_form = SubmitEditorForm(
                exercise_concrete_identity, editor_textarea_attrs
            )
        return cls._view(
            request,
            user_authority,
            organization,
            course,
            exercise,
            submit_editor_form=submit_editor_form,
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_SUBMIT_SUBMISSION
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        exercise: Exercise,
    ) -> HttpResponse:
        is_trial_allowed = is_trial_on_exercise_allowed(exercise, user_authority)
        if not is_trial_allowed:
            messages.error(request, "Try check is not available.")
            return cls._view(request, user_authority, organization, course, exercise)

        editor_textarea_attrs = {
            "id": f"id_view_exercise_concrete_editor__{exercise.name}",
            "class": " ".join(("view_exercise_editor",)),
        }
        submit_editor_form = SubmitEditorForm(None, editor_textarea_attrs, request.POST)

        is_valid_submission: bool = True
        while True:  # break-able if
            # 同時提出数チェック（負荷制御のため）（評価中のもののみ）
            simultaneous_trial_submissions = (
                Submission.objects.filter(
                    submission_type=SubmissionTypeEnum.TRIAL,
                    submitted_by=request.user,
                    evaluated_at__isnull=True,
                )
                .exclude(external_submission_id=None)
                .count()
            )
            print(f"{simultaneous_trial_submissions=}")

            if simultaneous_trial_submissions >= _MAX_SIMULTANEOUS_TRIAL_EVALUATIONS:
                is_valid_submission = False
                messages.error(
                    request,
                    "Too many simultaneous check trials. Please wait before post a new.",
                )
                break

            # 提出期限チェックは上部で既に行われている

            # 提出フォームの確認
            if not submit_editor_form.is_valid():
                is_valid_submission = False
                messages.error(request, "Your check trial is invalid.")
                break

            # 提出課題内容の最新性確認
            exercise_concrete_identity = ExerciseConcreteIdentity(
                name=exercise.name,
                version=exercise.latest_version,
                concrete_hash=exercise.latest_concrete_hash,
            )
            submitted_identity = ExerciseConcreteIdentity(
                name=submit_editor_form.cleaned_data["exercise_name"],
                version=submit_editor_form.cleaned_data["exercise_version"],
                concrete_hash=submit_editor_form.cleaned_data["exercise_concrete_hash"],
            )
            if submitted_identity != exercise_concrete_identity:
                is_valid_submission = False
                messages.error(
                    request,
                    "Exercise you answered is outdated because the exercise is updated. Please solve it again.",
                )
                submit_editor_form = SubmitEditorForm(
                    exercise_concrete_identity, editor_textarea_attrs
                )

            break

        if not is_valid_submission:
            return cls._view(
                request,
                user_authority,
                organization,
                course,
                exercise,
                submit_editor_form=submit_editor_form,
            )

        submission_source = submit_editor_form.cleaned_data["submission_source"]
        trial_submission = insert_trial_submission(
            organization, course, exercise, request.user, submission_source
        )

        try:
            send_submission_to_judger(
                trial_submission, submission_source=submission_source
            )
        except Exception:  # pylint:disable=broad-except
            SLACK_NOTIFIER.error(
                "Failed to send submission to judger.", traceback.format_exc()
            )
            traceback.print_exc()

        s_eb64 = encode_submission_id(course, trial_submission.id)

        return redirect(
            "submission/view",
            o_name=organization.name,
            c_name=course.name,
            s_eb64=s_eb64,
        )
