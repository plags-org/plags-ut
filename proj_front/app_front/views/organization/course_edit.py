import datetime
from typing import ClassVar, Dict, Optional, Type, Union

from django.contrib import messages
from django.forms import Form
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.course import get_courses_and_choices
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.plags_form_model_data import (
    DatetimeConverter,
    KeepAsIsModel,
    ModelFormFieldConverter,
    OptionalDatetimeConverter,
    PlagsFormModelData,
    TargetCourseList,
    build_batch_edit_form,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.plags_utils.structured_form import StructuredForm
from app_front.forms import EditCourseForm
from app_front.models import Course, Organization, UserAuthorityEnum
from app_front.utils.auth_util import (
    RequestContext,
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
)
from app_front.utils.exception_util import ExceptionHandler
from app_front.utils.time_util import get_current_datetime


class OrganizationCourseEditFormModelData(PlagsFormModelData[Course]):
    is_registerable: Union[KeepAsIsModel, bool]

    exercise_default_begins_at: Union[KeepAsIsModel, datetime.datetime]
    exercise_default_opens_at: Union[KeepAsIsModel, datetime.datetime]
    exercise_default_checks_at: Union[KeepAsIsModel, Optional[datetime.datetime]]
    exercise_default_closes_at: Union[KeepAsIsModel, datetime.datetime]
    exercise_default_ends_at: Union[KeepAsIsModel, datetime.datetime]
    exercise_default_is_shared_after_confirmed: Union[KeepAsIsModel, bool]
    exercise_default_score_visible_from: Union[KeepAsIsModel, UserAuthorityEnum]
    exercise_default_remarks_visible_from: Union[KeepAsIsModel, UserAuthorityEnum]

    __field_converters__: ClassVar[Dict[str, Type[ModelFormFieldConverter]]] = dict(
        exercise_default_begins_at=DatetimeConverter,
        exercise_default_opens_at=DatetimeConverter,
        exercise_default_checks_at=OptionalDatetimeConverter,
        exercise_default_closes_at=DatetimeConverter,
        exercise_default_ends_at=DatetimeConverter,
    )


EditOrganizationCourseForm: Type = build_batch_edit_form(
    "EditOrganizationCourseForm",
    EditCourseForm,
    base_type=StructuredForm,
    include_fields=frozenset(
        {
            "_group_basics",
            "is_registerable",
            "_group_defaults",
            "exercise_default_begins_at",
            "exercise_default_opens_at",
            "exercise_default_checks_at",
            "exercise_default_closes_at",
            "exercise_default_ends_at",
            "exercise_default_is_shared_after_confirmed",
            "exercise_default_score_visible_from",
            "exercise_default_remarks_visible_from",
        }
    ),
    exclude_fields=frozenset(
        {
            "name",
            "title",
        }
    ),
)


class OrganizationCourseEditView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        form: Optional[Form] = None,
    ) -> HttpResponse:
        courses, course_choices = get_courses_and_choices(organization)
        if form is None:
            # context = RequestContext.from_legacy(request, user_authority, organization)
            form = EditOrganizationCourseForm(
                # initial=OrganizationCourseEditFormModelData.from_model(course).to_form_initial(context),
                course_choices=course_choices,
            )
        return render(
            request,
            "organization/course_edit.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                courses=courses,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION,)
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        courses, course_choices = get_courses_and_choices(organization)
        form = EditOrganizationCourseForm(request.POST, course_choices=course_choices)
        if not form.is_valid():
            return cls._view(request, user_authority, organization, form=form)

        request_user = get_request_user_safe(request)

        with ExceptionHandler("Update course settings (batch)", request):
            context = RequestContext.from_legacy(request, user_authority, organization)
            incoming_model_data = (
                OrganizationCourseEditFormModelData.from_form_cleaned_data_for_patch(
                    context, form.cleaned_data
                )
            )
            target_courses = TargetCourseList(
                target_course_names=form.cleaned_data["courses"]
            )
            target_course_name_set = frozenset(target_courses.target_course_names)
            for course in courses:
                if course.name not in target_course_name_set:
                    continue
                current_model_data = OrganizationCourseEditFormModelData.from_model(
                    course
                )

                if diffs := current_model_data.detect_diffs_for_patch(
                    incoming_model_data
                ):
                    incoming_model_data.apply_to_model_for_patch(course)
                    course.edited_at = get_current_datetime()
                    course.edited_by = request_user
                    course.save()
                    messages.success(
                        request, f"[{course.name}] Updated: {tuple(diffs)}"
                    )
                else:
                    messages.info(request, f"[{course.name}] No changes")

            return redirect(
                "organization/course/edit",
                o_name=organization.name,
            )

        # ATTENTION this part is reachable (when exception occurred in ExceptionHandler)
        return cls._view(request, user_authority, organization, form=form)
