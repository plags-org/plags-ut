import dataclasses
import mimetypes
from typing import Iterator

from django.http.request import HttpRequest
from django.http.response import HttpResponse

from app_front.core.course_user import get_organization_course_users
from app_front.core.data_export import (
    convert_dataclasses_to_csv_str,
    iso8601_on_user_timezone,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import CourseUser, Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys


@dataclasses.dataclass
class ExportFormatOrganizationCourseUser:
    username: str
    student_card_number: str
    fullname: str
    added_at: str
    added_by: str
    authority: str
    permitted: str
    email: str
    course: str


class OrganizationCourseUserExportView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION
    )
    def _get(cls, request: HttpRequest, organization: Organization) -> HttpResponse:
        organization_course_users = get_organization_course_users(organization)
        user_timezone = request.user.timezone

        def convert_course_user_to_row(
            course_user: CourseUser,
        ) -> ExportFormatOrganizationCourseUser:
            return ExportFormatOrganizationCourseUser(
                username=course_user.user.username,
                student_card_number=course_user.user.student_card_number,
                fullname=course_user.user.full_name,
                added_at=iso8601_on_user_timezone(course_user.added_at, user_timezone),
                added_by=course_user.added_by.username,
                authority=course_user.authority.split("_", 1)[1],
                permitted=course_user.is_active,
                email=course_user.user.email,
                course=course_user.course.name,
            )

        def data_gen() -> Iterator[ExportFormatOrganizationCourseUser]:
            for course_user in organization_course_users:
                yield convert_course_user_to_row(course_user)

        file_content = convert_dataclasses_to_csv_str(
            ExportFormatOrganizationCourseUser, data_gen()
        )


        file_name = f"export_organization_course_users__{organization.name}.csv"
        response = HttpResponse(
            content_type=mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )
        response["Content-Disposition"] = f'attachment; filename="{file_name}"'
        response.write(file_content)
        return response
