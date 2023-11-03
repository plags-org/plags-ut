from typing import Iterable, Optional

from django.contrib import messages
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.oc_user import (
    AVAILABLE_ORGANIZATION_FACULTY_USER_AUTHORITY_CHOICES,
    ORGANIZATION_FACULTY_USER_DEFAULT_AUTHORITY_CHOICE,
    UserAuthorityCode,
    get_oc_user_choices,
    get_sorted_organization_users,
)
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.forms import KEY_REMOVE, MetaOCChangeUserForm
from app_front.models import Organization, OrganizationUser, User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.models_util import DjangoChoiceFieldChoices
from app_front.utils.time_util import get_current_datetime


class OrganizationFacultyUserChangeView(AbsPlagsView):
    # NOTE organization には faculty user しか所属しない

    MANIPULATE_ACTION: str = "Change"
    MANIPULATE_DESCRIPTION: str = "Change authority of user in"

    USER_AUTHORITY_CHOICES: DjangoChoiceFieldChoices = (
        AVAILABLE_ORGANIZATION_FACULTY_USER_AUTHORITY_CHOICES
    )
    USER_DEFAULT_AUTHORITY: UserAuthorityCode = (
        ORGANIZATION_FACULTY_USER_DEFAULT_AUTHORITY_CHOICE
    )

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        organization_users: Iterable[OrganizationUser],
        form: Optional[MetaOCChangeUserForm] = None,
    ) -> HttpResponse:
        if form is None:
            user_choices = get_oc_user_choices(organization_users)

            form = MetaOCChangeUserForm(
                user_choices,
                user_authority_choices=cls.USER_AUTHORITY_CHOICES,
                initial=dict(user_authority=cls.USER_DEFAULT_AUTHORITY),
            )
        return render(
            request,
            "meta_oc/manipulate_user.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                meta_oc_manipulate_action=cls.MANIPULATE_ACTION,
                meta_oc_manipulate_description=cls.MANIPULATE_DESCRIPTION,
                meta_oc_type="organization",
                meta_oc=organization,
                meta_oc_users=organization_users,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION,)
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
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_EDIT_ORGANIZATION,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        organization_users = get_sorted_organization_users(organization)

        user_choices = get_oc_user_choices(organization_users)
        form = MetaOCChangeUserForm(user_choices, request.POST)

        if not form.is_valid():
            return cls._view(
                request, user_authority, organization, organization_users, form=form
            )

        changed_user_id = form.cleaned_data["user"]
        changed_user_authority = form.cleaned_data["user_authority"]

        try:
            organization_user = OrganizationUser.objects.get(
                organization=organization,
                user_id=changed_user_id,
            )
            if changed_user_authority == KEY_REMOVE:
                OrganizationUser.objects.filter(
                    organization=organization,
                    user_id=changed_user_id,
                ).delete()
                messages.success(
                    request,
                    f"User [{organization_user.user.username}] successfully removed.",
                )
            elif organization_user.authority != changed_user_authority:
                change_detail = (
                    f"{organization_user.authority} => {changed_user_authority}"
                )
                organization_user.authority = changed_user_authority
                organization_user.authority_updated_at = get_current_datetime()
                organization_user.save()
                messages.success(
                    request,
                    f"User [{organization_user.user.username}] successfully updated. ({change_detail})",
                )
            else:
                messages.info(request, "No change detected.")
        except OrganizationUser.DoesNotExist:
            user = User.objects.get(id=changed_user_id)
            messages.error(
                request,
                f'User "{user.username}" has already removed from organization.',
            )

        return redirect(
            "organization_user/change_faculty",
            o_name=organization.name,
        )
