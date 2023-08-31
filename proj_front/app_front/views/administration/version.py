import traceback

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.application_version import (
    APPLICATION_MAJOR_VERSION,
    APPLICATION_MINOR_VERSION,
    APPLICATION_PATCH_VERSION,
    get_current_application_data_version,
)
from app_front.core.const import CURRENT_GIT_DESCRIBE_FILEPATH
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import ApplicationDataVersionHistory
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


def _get_application_git_revision() -> str:
    try:
        with open(CURRENT_GIT_DESCRIBE_FILEPATH, encoding="utf_8") as file:
            return file.read().strip()
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        SLACK_NOTIFIER.error(
            "Issue: _get_application_git_revision failed with unexpected Exception",
            traceback.format_exc(),
        )
        return "(Error reading application_git_revision)"


class AdministrationVersionView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.IS_SUPERUSER
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        application_data_version_histories = (
            ApplicationDataVersionHistory.objects.order_by("created_at").all()
        )

        current_application_version = dict(
            major_version=APPLICATION_MAJOR_VERSION,
            minor_version=APPLICATION_MINOR_VERSION,
            patch_version=APPLICATION_PATCH_VERSION,
        )
        current_application_data_version = get_current_application_data_version()
        current_application_git_revision = _get_application_git_revision()

        return render(
            request,
            "administration/version.html",
            dict(
                user_authority=user_authority,
                application_data_version_histories=application_data_version_histories,
                current_application_version=current_application_version,
                current_application_data_version=current_application_data_version,
                current_application_git_revision=current_application_git_revision,
            ),
        )
