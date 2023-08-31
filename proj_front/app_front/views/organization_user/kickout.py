import traceback
from typing import Final, List, Tuple

from django.contrib import messages
from django.contrib.messages.constants import SUCCESS, WARNING
from django.db import IntegrityError, transaction
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.oc_user import get_sorted_organization_users
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import MetaOCKickoutUsersForm
from app_front.models import Organization, OrganizationUser, User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.exception_util import SystemResponsibleException
from app_front.utils.time_util import get_current_datetime

MessageLevel = int


class OrganizationUserKickoutView(AbsPlagsView):
    MANIPULATE_ACTION: Final[str] = "Kickout"
    MANIPULATE_DESCRIPTION: Final[str] = "Kickout users in"

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        *,
        form: MetaOCKickoutUsersForm = None,
    ) -> HttpResponse:
        organization_users = get_sorted_organization_users(organization)
        if form is None:
            form = MetaOCKickoutUsersForm()
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
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_ORGANIZATION_USER
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_ORGANIZATION_USER
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        form = MetaOCKickoutUsersForm(request.POST)
        if not form.is_valid():
            return cls._view(request, user_authority, organization, form=form)

        clean_usernames = form.cleaned_data["clean_usernames"]
        try:
            message_list: List[Tuple[MessageLevel, str]] = []
            with transaction.atomic():
                for username in clean_usernames:
                    try:
                        user = User.objects.get(username=username)
                        organization_user = OrganizationUser.objects.get(
                            organization=organization, user=user
                        )
                    except User.DoesNotExist:
                        message_list.append(
                            (WARNING, f"User [{username}] does not exist.")
                        )
                        continue
                    except OrganizationUser.DoesNotExist:
                        message_list.append(
                            (
                                WARNING,
                                f"User [{username}] is not a member of organization [{organization.name}].",
                            )
                        )
                        continue

                    organization_user.is_active = False
                    organization_user.is_active_updated_at = get_current_datetime
                    organization_user.is_active_updated_by = request.user
                    organization_user.save()

                    message_list.append(
                        (
                            SUCCESS,
                            f"User [{username}] kicked out from organization [{organization.name}]",
                        )
                    )

        except IntegrityError as exc:
            SLACK_NOTIFIER.error(
                "Issue: organization_user/kickout failed with IntegrityError",
                traceback.format_exc(),
            )
            traceback.print_exc()
            raise SystemResponsibleException(exc) from exc

        except Exception as exc:  # pylint: disable=broad-except
            SLACK_NOTIFIER.error(
                "Issue: organization_user/kickout failed unexpectedly",
                traceback.format_exc(),
            )
            traceback.print_exc()
            raise SystemResponsibleException(exc) from exc

        for level, message in message_list:
            messages.add_message(request, level, message)

        return redirect("organization_user/kickout", o_name=organization.name)
