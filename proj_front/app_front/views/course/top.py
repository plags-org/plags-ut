import json
from typing import Optional

from django.http import Http404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.course import get_course_info_for_authority
from app_front.core.exercise import get_visible_exercises
from app_front.core.exercise_master import (
    add_messages_to_request,
    get_exercise_master_upload_options,
    import_exercise_masters,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.submission import get_exercise_submissions_for_course_top
from app_front.core.submission_parcel import process_submission_parcel
from app_front.forms import (
    SubmitSubmissionParcelForm,
    UploadExerciseForm,
    UploadExerciseFormForm,
)
from app_front.models import Course, CourseTopNoticeByOrganization, Organization
from app_front.utils.auth_util import (
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
    raise_if_lacks_user_authority,
)
from app_front.utils.exception_util import ExceptionHandler, SystemLogicalError
from app_front.utils.parameter_decoder import (
    encode_submission_parcel_id,
    get_exercise_info,
    get_exercise_info_published,
)


class CourseTopView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(
            UserAuthorityCapabilityKeys.CAN_VIEW_COURSE,
            UserAuthorityCapabilityKeys.CAN_VIEW_COURSE_PUBLISHED,
        )
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
        require_capabilities=(
            UserAuthorityCapabilityKeys.CAN_SUBMIT_SUBMISSION,
            UserAuthorityCapabilityKeys.CAN_CREATE_EXERCISE,
        )
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        if "answer_submit" in request.POST:
            return cls._post_answer_submit(
                request, user_authority, organization, course
            )
        if "exercise_upload" in request.POST:
            return cls._post_exercise_upload(
                request, user_authority, organization, course
            )
        raise Http404

    @classmethod
    def _post_answer_submit(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        raise_if_lacks_user_authority(
            request, user_authority, UserAuthorityCapabilityKeys.CAN_SUBMIT_SUBMISSION
        )

        form = SubmitSubmissionParcelForm(request.POST, request.FILES)
        if not form.is_valid():
            return cls._view(
                request, user_authority, organization, course, answer_submit_form=form
            )

        with ExceptionHandler("Process SubmissionParcel", request):
            submission_parcel = process_submission_parcel(
                request, organization, course, form
            )
            sp_eb64 = encode_submission_parcel_id(course, submission_parcel.id)
            return redirect(
                "submission_parcel/view",
                o_name=organization.name,
                c_name=course.name,
                sp_eb64=sp_eb64,
            )

        # ATTENTION ExceptionHandler は例外を吸収するのでここは通過しうる、デッドコードではない
        return cls._view(request, user_authority, organization, course)

    @classmethod
    def _post_exercise_upload(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        raise_if_lacks_user_authority(
            request, user_authority, UserAuthorityCapabilityKeys.CAN_CREATE_EXERCISE
        )

        form = UploadExerciseForm(request.POST, request.FILES)
        if not form.is_valid():
            return cls._view(
                request, user_authority, organization, course, exercise_upload_form=form
            )

        upload_file = form.cleaned_data["upload_file"]
        upload_options = get_exercise_master_upload_options(form)

        job_result = import_exercise_masters(
            request, organization, course, upload_file, upload_options
        )
        add_messages_to_request(request, job_result.messages)

        if not job_result.is_successful:
            return cls._view(
                request, user_authority, organization, course, exercise_upload_form=form
            )

        return redirect(
            "course/top",
            o_name=organization.name,
            c_name=course.name,
        )

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        /,
        *,
        answer_submit_form: Optional[SubmitSubmissionParcelForm] = None,
        exercise_upload_form: Optional[UploadExerciseForm] = None,
        exercise_form_upload_form: Optional[UploadExerciseFormForm] = None,
    ) -> HttpResponse:
        if answer_submit_form is None:
            answer_submit_form = SubmitSubmissionParcelForm()
        if exercise_upload_form is None:
            exercise_upload_form = UploadExerciseForm()
        if exercise_form_upload_form is None:
            exercise_form_upload_form = UploadExerciseFormForm()

        course_info = get_course_info_for_authority(
            organization, course, user_authority
        )

        if user_authority["can_view_exercise"]:
            exercise_info_getter = get_exercise_info
        elif user_authority["can_view_exercise_until_end"]:
            exercise_info_getter = get_exercise_info
        elif user_authority["can_view_course_published"]:
            exercise_info_getter = get_exercise_info_published
        else:
            raise SystemLogicalError("Should never come here")

        course_top_notice_by_organization_list = [
            course_top_notice_by_organization
            for course_top_notice_by_organization in CourseTopNoticeByOrganization.objects.filter(
                organization=organization, is_public_to_students=True
            )
            if course.name
            in json.loads(course_top_notice_by_organization.target_course_name_list)
        ]

        exercises = list(get_visible_exercises(user_authority, course))
        exercise_info_list = [
            exercise_info_getter(organization, exercise) for exercise in exercises
        ]
        # 自分の期限内提出物があれば課題に紐付けるので取ってくる
        request_user = get_request_user_safe(request)
        exercise_submissions = get_exercise_submissions_for_course_top(
            course, request_user
        )
        # if ...:
        #     exercise_upload_form = None

        return render(
            request,
            "course/top.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                course_top_notice_by_organization_list=course_top_notice_by_organization_list,
                course_info=course_info,
                exercises=exercises,
                exercise_info_list=exercise_info_list,
                exercise_submissions=exercise_submissions,
                answer_submit_form=answer_submit_form,
                exercise_upload_form=exercise_upload_form,
                exercise_form_upload_form=exercise_form_upload_form,
            ),
        )
