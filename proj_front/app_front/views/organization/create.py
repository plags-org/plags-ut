from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.organization import create_organization
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import CreateOrganizationForm
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict


class OrganizationCreateView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        *,
        form: CreateOrganizationForm = None,
    ) -> HttpResponse:
        del user_authority
        if form is None:
            form = CreateOrganizationForm()
        return render(request, "organization/create.html", dict(form=form))

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
        form = CreateOrganizationForm(request.POST)
        if not form.is_valid():
            return cls._view(request, user_authority, form=form)

        name = form.cleaned_data["name"]
        create_organization(
            name=name,
            request_user=get_request_user_safe(request),
        )

        return redirect("organization/top", o_name=name)
