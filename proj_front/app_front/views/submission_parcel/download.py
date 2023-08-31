import mimetypes
import urllib.parse

from django.contrib.auth.decorators import login_required
from django.http.response import Http404, HttpResponse

from app_front.core.submission_parcel import workaround_supply_default_file_name
from app_front.utils.auth_util import (
    annex_user_authority,
    check_and_notify_exception,
    check_user_authority,
)
from app_front.utils.parameter_decoder import get_organization_course_submission_parcel


@login_required
@check_and_notify_exception
@annex_user_authority
@check_user_authority("can_submit_submission")
def _get(request, user_authority, *_args, **kwargs):
    (
        _organization,
        _course,
        submission_parcel,
    ) = get_organization_course_submission_parcel(**kwargs)

    is_reviewer = user_authority.get("can_review_submission")
    if not is_reviewer:
        # この人は自分の提出しか確認できないべき
        if submission_parcel.submitted_by != request.user:
            # NOTE 遅延時間の違いにより「提出が存在する」ことは露呈してしまう恐れがある
            raise Http404()

    file_name = workaround_supply_default_file_name(
        submission_parcel.submission_parcel_file_initial_name
    )
    # NOTE 学生にも提供するので renaming は行わないことになった
    # file_name = f'plags_ut.{organization.name}.{course.name}.sp.{submission_parcel.id}.{file_name}'
    file_content = submission_parcel.submission_parcel_file.read()

    def get_utf8_safe_attachment_content_disposition(file_name: str) -> str:
        escaped_file_name = urllib.parse.quote(file_name)
        return "; ".join(
            (
                "attachment",
                f'filename="{escaped_file_name}"',
                f'''filename*=UTF-8''"{escaped_file_name}"''',
            )
        )

    response = HttpResponse(
        content_type=mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    )
    response["Content-Disposition"] = get_utf8_safe_attachment_content_disposition(
        file_name
    )
    response.write(file_content)

    return response


def view_submission_parcel_download(request, *args, **kwargs):
    return _get(request, *args, **kwargs)
