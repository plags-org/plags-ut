from typing import Dict

from django.http.request import HttpRequest
from django.http.response import Http404, HttpResponse
from django.shortcuts import redirect, render

from app_front.core.course import get_course_choices, get_courses_and_choices
from app_front.core.exercise_master import (
    ImportExerciseMastersJobResult,
    add_messages_to_request,
    get_exercise_master_upload_options,
    import_exercise_masters,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.types import CourseName
from app_front.forms import UploadExerciseForeachCourseForm
from app_front.models import Course, Exercise, Organization, OrganizationUser
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class OrganizationTopView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        *,
        exercise_upload_form: UploadExerciseForeachCourseForm = None,
    ) -> HttpResponse:
        courses, course_choices = get_courses_and_choices(organization)
        if exercise_upload_form is None:
            exercise_upload_form = UploadExerciseForeachCourseForm(
                course_choices=course_choices
            )

        exercises = Exercise.objects.filter(course__organization=organization)
        organization_users = OrganizationUser.objects.filter(
            organization=organization, is_active=True
        )

        return render(
            request,
            "organization/top.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                courses=courses,
                exercises=exercises,
                organization_users=organization_users,
                exercise_upload_form=exercise_upload_form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_VIEW_ORGANIZATION
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
        require_capabilities=UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        if "exercise_upload" in request.POST:
            return cls._post_exercise_upload(request, user_authority, organization)
        raise Http404()

    @classmethod
    def _post_exercise_upload(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        course_choices = get_course_choices(organization)
        form = UploadExerciseForeachCourseForm(
            request.POST, request.FILES, course_choices=course_choices
        )
        if not form.is_valid():
            return cls._view(request, user_authority, organization)

        target_course_names = form.cleaned_data["courses"]
        upload_file = form.cleaned_data["upload_file"]
        upload_options = get_exercise_master_upload_options(form)

        job_results: Dict[CourseName, ImportExerciseMastersJobResult] = {}
        for course_name in target_course_names:
            try:
                course = Course.objects.get(name=course_name, is_active=True)
            except Course.DoesNotExist:
                error_message = f"course [{course_name}] does not exist."
                job_results[course_name] = ImportExerciseMastersJobResult.make_error(
                    error_message
                )
                continue
            upload_file.seek(0)
            job_result = import_exercise_masters(
                request, organization, course, upload_file, upload_options
            )
            job_result.add_prefix_to_messages(f"[{course_name}] ")
            job_results[course_name] = job_result
            add_messages_to_request(request, job_result.messages)

        return redirect(
            "organization/top",
            o_name=organization.name,
        )
