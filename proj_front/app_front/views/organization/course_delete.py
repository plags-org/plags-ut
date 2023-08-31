from typing import ClassVar, Dict, Optional, Type, Union

from django.contrib import messages
from django.forms import Form
from django.http import Http404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.course import (
    get_courses_and_choices,
    get_deleted_courses,
    to_course_choices,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.plags_form_model_data import (
    KeepAsIsModel,
    ModelFormFieldConverter,
    PlagsFormModelData,
    TargetCourseList,
    build_batch_edit_form,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.plags_utils.structured_form import StructuredForm
from app_front.forms import DeleteCourseForm, RestoreCourseForm
from app_front.models import Course, Organization
from app_front.utils.auth_util import (
    RequestContext,
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
    raise_if_lacks_user_authority,
)
from app_front.utils.exception_util import ExceptionHandler
from app_front.utils.time_util import get_current_datetime


class OrganizationCourseDeleteFormModelData(PlagsFormModelData[Course]):
    is_active: Union[KeepAsIsModel, bool]

    __field_converters__: ClassVar[Dict[str, Type[ModelFormFieldConverter]]] = {}


DeleteOrganizationCourseForm: Type = build_batch_edit_form(
    "DeleteOrganizationCourseForm",
    DeleteCourseForm,
    base_type=StructuredForm,
    include_fields=frozenset({"is_active"}),
    exclude_fields=frozenset({}),
    constant_fields={"is_active": False},
)

RestoreOrganizationCourseForm: Type = build_batch_edit_form(
    "RestoreOrganizationCourseForm",
    RestoreCourseForm,
    base_type=StructuredForm,
    include_fields=frozenset({"is_active"}),
    exclude_fields=frozenset({}),
    constant_fields={"is_active": True},
)


class OrganizationCourseDeleteView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        *,
        delete_form: Optional[Form] = None,
        restore_form: Optional[Form] = None,
    ) -> HttpResponse:
        courses, course_choices = get_courses_and_choices(organization)
        deleted_courses = get_deleted_courses(organization)
        deleted_course_choices = to_course_choices(deleted_courses)

        if delete_form is None:
            delete_form = DeleteOrganizationCourseForm(
                course_choices=course_choices,
            )
        if restore_form is None:
            restore_form = RestoreOrganizationCourseForm(
                course_choices=deleted_course_choices,
            )

        return render(
            request,
            "organization/course_delete.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                courses=courses,
                deleted_courses=deleted_courses,
                delete_form=delete_form,
                restore_form=restore_form,
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
        if "delete_courses" in request.POST:
            return cls._post_delete(request, user_authority, organization)
        if "restore_courses" in request.POST:
            return cls._post_restore(request, user_authority, organization)
        raise Http404

    @classmethod
    def _post_delete(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        courses, course_choices = get_courses_and_choices(organization)
        delete_form = DeleteOrganizationCourseForm(
            request.POST, course_choices=course_choices
        )
        if not delete_form.is_valid():
            return cls._view(
                request, user_authority, organization, delete_form=delete_form
            )

        request_user = get_request_user_safe(request)

        with ExceptionHandler("Delete courses (batch)", request):
            context = RequestContext.from_legacy(request, user_authority, organization)
            incoming_model_data = (
                OrganizationCourseDeleteFormModelData.from_form_cleaned_data_for_patch(
                    context, delete_form.cleaned_data
                )
            )
            target_courses = TargetCourseList(
                target_course_names=delete_form.cleaned_data["courses"]
            )
            target_course_name_set = frozenset(target_courses.target_course_names)
            for course in courses:
                if course.name not in target_course_name_set:
                    continue
                current_model_data = OrganizationCourseDeleteFormModelData.from_model(
                    course
                )

                if current_model_data.detect_diffs_for_patch(incoming_model_data):
                    incoming_model_data.apply_to_model_for_patch(course)
                    course.is_active_updated_at = get_current_datetime()
                    course.is_active_updated_by = request_user
                    course.save()
                    messages.success(request, f"[{course.name}] Deleted.")
                else:
                    messages.info(request, f"[{course.name}] No changes.")

            return redirect(
                "organization/course/delete",
                o_name=organization.name,
            )

        # ATTENTION this part is reachable (when exception occurred in ExceptionHandler)
        return cls._view(request, user_authority, organization, delete_form=delete_form)

    @classmethod
    def _post_restore(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        raise_if_lacks_user_authority(
            request, user_authority, UserAuthorityCapabilityKeys.IS_SUPERUSER
        )

        deleted_courses = get_deleted_courses(organization)
        deleted_course_choices = to_course_choices(deleted_courses)
        restore_form = RestoreOrganizationCourseForm(
            request.POST, course_choices=deleted_course_choices
        )
        if not restore_form.is_valid():
            return cls._view(
                request, user_authority, organization, restore_form=restore_form
            )

        request_user = get_request_user_safe(request)

        with ExceptionHandler("Restore courses (batch)", request):
            context = RequestContext.from_legacy(request, user_authority, organization)
            incoming_model_data = (
                OrganizationCourseDeleteFormModelData.from_form_cleaned_data_for_patch(
                    context, restore_form.cleaned_data
                )
            )
            target_courses = TargetCourseList(
                target_course_names=restore_form.cleaned_data["courses"]
            )
            target_course_name_set = frozenset(target_courses.target_course_names)
            for course in deleted_courses:
                if course.name not in target_course_name_set:
                    continue
                current_model_data = OrganizationCourseDeleteFormModelData.from_model(
                    course
                )

                if current_model_data.detect_diffs_for_patch(incoming_model_data):
                    incoming_model_data.apply_to_model_for_patch(course)
                    course.is_active_updated_at = get_current_datetime()
                    course.is_active_updated_by = request_user
                    course.save()
                    messages.success(request, f"[{course.name}] Restored.")
                else:
                    messages.info(request, f"[{course.name}] No changes.")

            return redirect(
                "organization/course/delete",
                o_name=organization.name,
            )

        # ATTENTION this part is reachable (when exception occurred in ExceptionHandler)
        return cls._view(
            request, user_authority, organization, restore_form=restore_form
        )
