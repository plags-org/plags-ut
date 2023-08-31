from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.custom_evaluation_tag import (
    CustomEvaluationTagManager,
    get_custom_evaluation_tags_for_authority,
)
from app_front.core.submission_parcel import process_submission_parcel
from app_front.forms import SubmitSubmissionParcelForm
from app_front.models import SubmissionParcel
from app_front.utils.auth_util import (
    annex_user_authority,
    check_and_notify_exception,
    check_user_authority,
)
from app_front.utils.exception_util import ExceptionHandler
from app_front.utils.parameter_decoder import (
    encode_submission_parcel_id,
    get_organization_course,
)


def get_seeable_submission_parcels(request, user_authority, organization, course):
    """
    ログインユーザーに閲覧が許されている提出物のリストを得る
    """

    filter_condition = dict(
        organization=organization,
        course=course,
    )

    # レビュー権限がなければ自分の提出しか見れないべき
    if not user_authority.get("can_review_submission"):
        filter_condition["submitted_by"] = request.user

    return (
        SubmissionParcel.objects.filter(**filter_condition)
        .order_by("-submitted_at")
        .select_related("submitted_by")
    )


def render_submission_page(
    request, user_authority, organization, course, form
) -> HttpResponse:
    submission_parcels = get_seeable_submission_parcels(
        request, user_authority, organization, course
    )
    custom_evaluation_tags = get_custom_evaluation_tags_for_authority(
        organization, course, user_authority
    )
    custom_evaluation_tag_manager = CustomEvaluationTagManager(
        custom_evaluation_tags, user_authority
    )

    if not course.begins_to_ends():
        form = None

    return render(
        request,
        "submission_parcel/list.html",
        dict(
            user_authority=user_authority,
            organization=organization,
            course=course,
            form=form,
            submission_parcels=submission_parcels,
            custom_evaluation_tag_manager=custom_evaluation_tag_manager,
        ),
    )


@login_required
@check_and_notify_exception
@annex_user_authority
@check_user_authority("can_list_submission")
def _get(request, user_authority, *_args, **kwargs):
    organization, course = get_organization_course(**kwargs)

    form = SubmitSubmissionParcelForm()

    return render_submission_page(request, user_authority, organization, course, form)


@login_required
@check_and_notify_exception
@annex_user_authority
@check_user_authority("can_list_submission")
def _post(request, user_authority, *_args, **kwargs):
    organization, course = get_organization_course(**kwargs)

    form = SubmitSubmissionParcelForm(request.POST, request.FILES)

    if not form.is_valid():
        return render_submission_page(
            request, user_authority, organization, course, form
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

    # ATTENTION this part is reachable (when exception occurred in ExceptionHandler)
    form = SubmitSubmissionParcelForm()
    return render_submission_page(request, user_authority, organization, course, form)


def view_submission_parcel_list(request, *args, **kwargs):
    if request.method == "POST":
        return _post(request, *args, **kwargs)
    return _get(request, *args, **kwargs)
