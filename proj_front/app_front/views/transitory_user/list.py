from typing import Optional

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import render

from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.models import Organization, TransitoryUser
from app_front.utils.auth_util import (
    UserAuthorityCapabilityKeys,
    UserAuthorityDict,
    raise_if_lacks_user_authority,
)


class TransitoryUserListView(AbsPlagsView):
    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(
            UserAuthorityCapabilityKeys.CAN_INVITE_USER_TO_ORGANIZATION,
        )
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Optional[Organization],
    ) -> HttpResponse:
        users = TransitoryUser.objects.order_by("-id").select_related(
            "invited_by",
            "invited_organization",
            "invited_course",
        )
        if organization:
            users = users.filter(invited_organization=organization)
        else:
            # NOTE 組織の絞り込みなしで表示するにはより強い権限を要求する
            raise_if_lacks_user_authority(
                request, user_authority, UserAuthorityCapabilityKeys.CAN_INVITE_USER
            )
        return render(
            request,
            "transitory_user/list.html",
            dict(
                user_authority=user_authority,
                users=users,
                organization=organization,
            ),
        )
