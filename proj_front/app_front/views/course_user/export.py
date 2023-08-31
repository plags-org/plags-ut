import dataclasses
import mimetypes

from django.contrib.auth.decorators import login_required
from django.shortcuts import HttpResponse

from app_front.core.data_export import (
    convert_dataclasses_to_csv_str,
    iso8601_on_user_timezone,
)
from app_front.models import CourseUser
from app_front.utils.auth_util import (
    annex_user_authority,
    check_and_notify_exception,
    check_user_authority,
)
from app_front.utils.parameter_decoder import get_organization_course


@dataclasses.dataclass
class ExportFormatCourseUser:
    username: str
    student_card_number: str
    fullname: str
    added_at: str
    added_by: str
    authority: str
    permitted: str
    email: str


@login_required
@check_and_notify_exception
@annex_user_authority
@check_user_authority("can_edit_course")
def _get(request, _user_authority, *_args, **kwargs):
    organization, course = get_organization_course(**kwargs)
    user_timezone = request.user.timezone

    def convert_course_user_to_row(course_user: CourseUser) -> ExportFormatCourseUser:
        return ExportFormatCourseUser(
            username=course_user.user.username,
            student_card_number=course_user.user.student_card_number,
            fullname=course_user.user.full_name,
            added_at=iso8601_on_user_timezone(course_user.added_at, user_timezone),
            added_by=course_user.added_by.username,
            authority=course_user.authority.split("_", 1)[1],
            permitted=course_user.is_active,
            email=course_user.user.email,
        )

    course_users = (
        CourseUser.objects.filter(
            course=course,
        )
        .select_related(
            "user",
            "added_by",
        )
        .all()
    )

    def data_gen():
        for course_user in course_users:
            yield convert_course_user_to_row(course_user)

    file_content = convert_dataclasses_to_csv_str(ExportFormatCourseUser, data_gen())


    file_name = f"export_course_users__{organization.name}__{course.name}.csv"
    response = HttpResponse(
        content_type=mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    )
    response["Content-Disposition"] = f'attachment; filename="{file_name}"'
    response.write(file_content)
    return response


def view_course_user_export(request, *args, **kwargs):
    return _get(request, *args, **kwargs)
