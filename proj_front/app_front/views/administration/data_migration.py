from typing import Optional

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.config.config import APP_CONFIG
from app_front.core.application_version import (
    APPLICATION_MAJOR_VERSION,
    APPLICATION_MINOR_VERSION,
    APPLICATION_PATCH_VERSION,
    get_current_application_data_version,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.data_migration.main import migrate_data
from app_front.forms import AdministrationDataMigrationForm
from app_front.models import ApplicationDataVersionHistory
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.console_message import Tee



class AdministrationDataMigrationView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        *,
        form: Optional[AdministrationDataMigrationForm] = None,
        console_message: Optional[str] = None,
        is_successful: Optional[bool] = None,
    ) -> HttpResponse:
        application_data_version_histories = (
            ApplicationDataVersionHistory.objects.order_by("-created_at").all()
        )
        current_application_version = dict(
            major_version=APPLICATION_MAJOR_VERSION,
            minor_version=APPLICATION_MINOR_VERSION,
            patch_version=APPLICATION_PATCH_VERSION,
        )
        current_application_data_version = get_current_application_data_version()

        if form is None:
            form = AdministrationDataMigrationForm(initial=dict(verbose=True))

        return render(
            request,
            "administration/data_migration.html",
            dict(
                user_authority=user_authority,
                application_data_version_histories=application_data_version_histories,
                current_application_version=current_application_version,
                current_application_data_version=current_application_data_version,
                form=form,
                console_message=console_message,
                is_successful=is_successful,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.IS_SUPERUSER
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        return cls._view(request, user_authority)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.IS_SUPERUSER
    )
    def _post(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        form = AdministrationDataMigrationForm(request.POST)
        form.set_passphrase(APP_CONFIG.ADMINISTRATION.data_migration_passphrase)
        if not form.is_valid():
            return cls._view(request, user_authority, form=form)

        verbose = form.cleaned_data["verbose"]
        tee = Tee()
        is_successful = migrate_data(request, tee, verbose=verbose)
        return cls._view(
            request,
            user_authority,
            console_message=tee.full_str(),
            is_successful=is_successful,
        )
