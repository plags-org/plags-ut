import dataclasses
import datetime
import mimetypes
from typing import Iterable, Optional

from django.http.request import HttpRequest
from django.http.response import HttpResponse

from app_front.core.data_export import convert_dataclasses_to_csv_str
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


@dataclasses.dataclass
class ExportFormatUser:
    id: int
    username: str
    is_faculty: bool
    student_card_number: str
    fullname: str
    joined_at: datetime.datetime
    invited_by_id: Optional[int]
    permitted: bool
    is_superuser: bool
    email: Optional[str]
    google_id_info_sub: Optional[str]
    cooperate_on_research_anonymously: bool


class UserListExportFileView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_MANAGE_USER,)
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        del request, user_authority

        def convert_user_to_row(user: User) -> ExportFormatUser:
            return ExportFormatUser(
                id=user.id,
                username=user.username,
                is_faculty=user.is_faculty,
                student_card_number=user.student_card_number,
                fullname=user.full_name,
                joined_at=user.joined_at,
                invited_by_id=user.invited_by_id,
                permitted=user.is_active,
                is_superuser=user.is_superuser,
                email=user.email,
                google_id_info_sub=user.google_id_info_sub,
                cooperate_on_research_anonymously=user.flag_cooperate_on_research_anonymously,
            )

        users = User.objects.all()

        def data_gen() -> Iterable[ExportFormatUser]:
            for user in users:
                yield convert_user_to_row(user)

        file_content = convert_dataclasses_to_csv_str(ExportFormatUser, data_gen())


        file_name = "export_users.csv"
        response = HttpResponse(
            content_type=mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )
        response["Content-Disposition"] = f'attachment; filename="{file_name}"'
        response.write(file_content)
        return response
