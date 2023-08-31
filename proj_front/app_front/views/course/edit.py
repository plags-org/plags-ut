import datetime
from typing import ClassVar, Dict, FrozenSet, Optional, Type

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.course import get_course_info_for_authority
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.plags_form_model_data import (
    DatetimeConverter,
    ModelFormFieldConverter,
    OptionalDatetimeConverter,
    PlagsFormModelData,
    RemarksVisibleFromConverter,
    ScoreVisibleFromConverter,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import EditCourseDescriptionForm, EditCourseForm
from app_front.models import Course, Organization, UserAuthorityEnum
from app_front.utils.auth_util import (
    RequestContext,
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
)
from app_front.utils.exception_util import ExceptionHandler
from app_front.utils.time_util import get_current_datetime


class CourseEditFormModelData(PlagsFormModelData[Course]):
    name: str

    title: str

    is_registerable: bool

    exercise_default_begins_at: datetime.datetime
    exercise_default_opens_at: datetime.datetime
    exercise_default_checks_at: Optional[datetime.datetime]
    exercise_default_closes_at: datetime.datetime
    exercise_default_ends_at: datetime.datetime
    exercise_default_is_shared_after_confirmed: bool
    exercise_default_score_visible_from: UserAuthorityEnum
    exercise_default_remarks_visible_from: UserAuthorityEnum

    __key_translations__: ClassVar[Dict[str, str]] = dict(
        drive_resource_id="drive",
    )
    __field_converters__: ClassVar[Dict[str, Type[ModelFormFieldConverter]]] = dict(
        exercise_default_begins_at=DatetimeConverter,
        exercise_default_opens_at=DatetimeConverter,
        exercise_default_checks_at=OptionalDatetimeConverter,
        exercise_default_closes_at=DatetimeConverter,
        exercise_default_ends_at=DatetimeConverter,
        exercise_default_score_visible_from=ScoreVisibleFromConverter,
        exercise_default_remarks_visible_from=RemarksVisibleFromConverter,
    )
    __readonly_fields__: ClassVar[FrozenSet[str]] = frozenset(("name",))


class EditCourseView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        form: EditCourseForm = None,
    ) -> HttpResponse:
        if form is None:
            context = RequestContext.from_legacy(
                request, user_authority, organization, course
            )
            form = EditCourseForm(
                initial=CourseEditFormModelData.from_model(course).to_form_initial(
                    context
                )
            )
        return render(
            request,
            "course/edit.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_COURSE,)
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization, course)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_COURSE,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        request_user = get_request_user_safe(request)
        form = EditCourseForm(request.POST)
        if not form.is_valid():
            return cls._view(request, user_authority, organization, course, form=form)

        with ExceptionHandler("Update Course", request):
            context = RequestContext.from_legacy(
                request, user_authority, organization, course
            )
            incoming_model_data = CourseEditFormModelData.from_form_cleaned_data(
                context, form.cleaned_data
            )
            current_model_data = CourseEditFormModelData.from_model(course)

            if diffs := current_model_data.detect_diffs(incoming_model_data):
                incoming_model_data.apply_to_model(course)
                course.edited_at = get_current_datetime()
                course.edited_by = request_user
                course.save()
                messages.success(request, f"Updated: {tuple(diffs)}")
            else:
                messages.info(request, "No changes")

            return redirect(
                "course/edit",
                o_name=organization.name,
                c_name=course.name,
            )

        # ATTENTION this part is reachable (when exception occurred in ExceptionHandler)
        return cls._view(request, user_authority, organization, course, form=form)


class CourseDescriptionEditFormModelData(PlagsFormModelData[Course]):
    body: str


class EditCourseDescriptionView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        form: EditCourseDescriptionForm = None,
    ) -> HttpResponse:
        if form is None:
            context = RequestContext.from_legacy(
                request, user_authority, organization, course
            )
            form = EditCourseDescriptionForm(
                initial=CourseDescriptionEditFormModelData.from_model(
                    course
                ).to_form_initial(context)
            )

        course_info = get_course_info_for_authority(
            organization, course, user_authority
        )

        return render(
            request,
            "course/description_edit.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                course_info=course_info,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_COURSE,)
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization, course)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_COURSE,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        form = EditCourseDescriptionForm(request.POST)
        if not form.is_valid():
            return cls._view(request, user_authority, organization, course, form=form)

        with ExceptionHandler("Update Course", request):
            context = RequestContext.from_legacy(
                request, user_authority, organization, course
            )
            incoming_model_data = (
                CourseDescriptionEditFormModelData.from_form_cleaned_data(
                    context, form.cleaned_data
                )
            )
            current_model_data = CourseDescriptionEditFormModelData.from_model(course)

            if diffs := current_model_data.detect_diffs(incoming_model_data):
                incoming_model_data.apply_to_model(course)
                course.edited_at = get_current_datetime()
                course.edited_by = request.user
                course.save()
                messages.success(request, f"Updated: {tuple(diffs)}")
            else:
                messages.info(request, "No changes")

            return redirect(
                "course/description_edit",
                o_name=organization.name,
                c_name=course.name,
            )

        # ATTENTION this part is reachable (when exception occurred in ExceptionHandler)
        return cls._view(request, user_authority, organization, course, form=form)
