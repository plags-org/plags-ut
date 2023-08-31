from typing import Iterable

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.oc_user import (
    AVAILABLE_FACULTY_USER_AUTHORITY_CHOICES,
    FACULTY_USER_DEFAULT_AUTHORITY_CHOICE,
    get_non_oc_faculty_choices,
    get_sorted_organization_users,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.forms import MetaOCAddUserForm
from app_front.models import Organization, OrganizationUser
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.time_util import get_current_datetime


class OrganizationUserAddFacultyView(AbsPlagsView):
    MANIPULATE_ACTION: str = "Add"
    MANIPULATE_DESCRIPTION: str = "Add faculty user to"
    MANIPULATE_USER_LIST_HEADING: str = "Current organization users (faculty)"

    TEMPLATE_HTML_FILE_PATH: str = "meta_oc/manipulate_user.html"

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        organization_users: Iterable[OrganizationUser],
        form: MetaOCAddUserForm = None,
    ) -> HttpResponse:
        if form is None:
            user_choices = get_non_oc_faculty_choices(organization_users)
            form = MetaOCAddUserForm(
                user_choices,
                user_authority_choices=AVAILABLE_FACULTY_USER_AUTHORITY_CHOICES,
                initial=dict(user_authority=FACULTY_USER_DEFAULT_AUTHORITY_CHOICE),
            )

        return render(
            request,
            cls.TEMPLATE_HTML_FILE_PATH,
            dict(
                user_authority=user_authority,
                organization=organization,
                meta_oc_manipulate_action=cls.MANIPULATE_ACTION,
                meta_oc_manipulate_description=cls.MANIPULATE_DESCRIPTION,
                meta_oc_current_users_heading=cls.MANIPULATE_USER_LIST_HEADING,
                meta_oc_type="organization",
                meta_oc=organization,
                meta_oc_users=organization_users,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        organization_users = get_sorted_organization_users(organization)
        return cls._view(request, user_authority, organization, organization_users)

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
        organization_users = get_sorted_organization_users(organization)

        user_choices = get_non_oc_faculty_choices(organization_users)
        form = MetaOCAddUserForm(user_choices, request.POST)
        if not form.is_valid():
            return cls._view(
                request, user_authority, organization, organization_users, form=form
            )

        added_user_id = form.cleaned_data["user"]
        added_user_authority = form.cleaned_data["user_authority"]

        organization_user, is_created = OrganizationUser.objects.get_or_create(
            organization=organization,
            user_id=added_user_id,
            defaults=dict(
                added_by=request.user,
                is_active=True,
                is_active_updated_by=request.user,
                authority=added_user_authority,
                authority_updated_by=request.user,
            ),
        )
        if is_created:
            messages.success(
                request,
                f"User [{organization_user.user.username}] successfully added. ({added_user_authority})",
            )
        elif organization_user.authority != added_user_authority:
            change_detail = f"{organization_user.authority} => {added_user_authority}"
            organization_user.authority = added_user_authority
            organization_user.authority_updated_at = get_current_datetime()
            organization_user.save()
            messages.success(
                request,
                f"User [{organization_user.user.username}] successfully updated. ({change_detail})",
            )
        else:
            messages.info(request, "No change detected.")

        return redirect(
            "organization_user/add_faculty",
            o_name=organization.name,
        )
