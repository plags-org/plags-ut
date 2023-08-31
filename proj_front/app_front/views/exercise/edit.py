import datetime
from typing import ClassVar, Dict, Optional, Type

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.plags_form_model_data import (
    IsSharedAfterConfirmedConverter,
    ModelFormFieldConverter,
    OptionalDatetimeConverter,
    OptionalDriveResourceIDConverter,
    PlagsFormModelData,
    RemarksVisibleFromConverter,
    ScoreVisibleFromConverter,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import EditExerciseForm
from app_front.models import Course, Exercise, Organization, UserAuthorityEnum
from app_front.utils.auth_util import (
    RequestContext,
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
)
from app_front.utils.exception_util import ExceptionHandler
from app_front.utils.time_util import get_current_datetime


class ExerciseEditFormModelData(PlagsFormModelData[Exercise]):
    title: str
    begins_at: Optional[datetime.datetime]
    opens_at: Optional[datetime.datetime]
    checks_at: Optional[datetime.datetime]
    closes_at: Optional[datetime.datetime]
    ends_at: Optional[datetime.datetime]
    is_shared_after_confirmed: Optional[bool]
    score_visible_from: Optional[UserAuthorityEnum]
    remarks_visible_from: Optional[UserAuthorityEnum]
    is_draft: bool
    drive_resource_id: Optional[str]

    __key_translations__: ClassVar[Dict[str, str]] = dict(
        drive_resource_id="drive",
    )
    __field_converters__: ClassVar[Dict[str, Type[ModelFormFieldConverter]]] = dict(
        begins_at=OptionalDatetimeConverter,
        opens_at=OptionalDatetimeConverter,
        checks_at=OptionalDatetimeConverter,
        closes_at=OptionalDatetimeConverter,
        ends_at=OptionalDatetimeConverter,
        is_shared_after_confirmed=IsSharedAfterConfirmedConverter,
        score_visible_from=ScoreVisibleFromConverter,
        remarks_visible_from=RemarksVisibleFromConverter,
        drive_resource_id=OptionalDriveResourceIDConverter,
    )


class ExerciseEditView(AbsPlagsView):
    @staticmethod
    def _view(
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        exercise: Exercise,
        *,
        form: EditExerciseForm = None,
    ) -> HttpResponse:
        if form is None:
            context = RequestContext.from_legacy(
                request, user_authority, organization, course
            )
            form = EditExerciseForm(
                default_is_shared_after_confirmed=course.exercise_default_is_shared_after_confirmed,
                default_score_visible_from=UserAuthorityEnum(
                    course.exercise_default_score_visible_from
                ),
                default_remarks_visible_from=UserAuthorityEnum(
                    course.exercise_default_remarks_visible_from
                ),
                initial=ExerciseEditFormModelData.from_model(exercise).to_form_initial(
                    context
                ),
            )
        return render(
            request,
            "exercise/edit.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                exercise=exercise,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_EXERCISE,)
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        exercise: Exercise,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization, course, exercise)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_EXERCISE,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        exercise: Exercise,
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        form = EditExerciseForm(
            default_is_shared_after_confirmed=course.exercise_default_is_shared_after_confirmed,
            default_score_visible_from=UserAuthorityEnum(
                course.exercise_default_score_visible_from
            ),
            default_remarks_visible_from=UserAuthorityEnum(
                course.exercise_default_remarks_visible_from
            ),
            data=request.POST,
        )
        if not form.is_valid():
            return cls._view(
                request, user_authority, organization, course, exercise, form=form
            )

        with ExceptionHandler("Update Exercise", request):
            context = RequestContext.from_legacy(
                request, user_authority, organization, course
            )
            incoming_model_data = ExerciseEditFormModelData.from_form_cleaned_data(
                context, form.cleaned_data
            )
            current_model_data = ExerciseEditFormModelData.from_model(exercise)

            if diffs := current_model_data.detect_diffs(incoming_model_data):
                incoming_model_data.apply_to_model(exercise)
                exercise.edited_at = get_current_datetime()
                exercise.edited_by = request_user
                exercise.save()
                messages.success(request, f"Updated: {tuple(diffs)}")
            else:
                messages.info(request, "No changes")

            return redirect(
                "exercise/edit",
                o_name=organization.name,
                c_name=course.name,
                e_name=exercise.name,
            )

        # ATTENTION this part is reachable (when exception occurred in ExceptionHandler)
        return cls._view(
            request, user_authority, organization, course, exercise, form=form
        )
