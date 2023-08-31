import datetime
from typing import Optional

from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.course import CourseCreateData, create_course
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.forms import CreateCourseForm
from app_front.models import Organization
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.time_util import get_current_datetime


def _floor_hour(dt: datetime.datetime) -> datetime.datetime:
    return dt.replace(microsecond=0, second=0, minute=0)


def _N_weeks_later(dt: datetime.datetime, n: int) -> datetime.datetime:
    return dt + datetime.timedelta(days=7 * n)


class CreateCourseView(AbsPlagsView):
    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        *,
        form: Optional[CreateCourseForm] = None,
    ) -> HttpResponse:
        if form is None:
            begins_at = _floor_hour(get_current_datetime())
            opens_at = _N_weeks_later(begins_at, 2)
            closes_at = _N_weeks_later(opens_at, 15)
            ends_at = _N_weeks_later(closes_at, 2)
            form = CreateCourseForm(
                organization,
                initial=dict(
                    is_registerable=True,
                    exercise_default_begins_at=begins_at,
                    exercise_default_opens_at=opens_at,
                    exercise_default_checks_at=None,
                    exercise_default_closes_at=closes_at,
                    exercise_default_ends_at=ends_at,
                    exercise_default_is_shared_after_confirmed=False,
                ),
            )
        return render(
            request,
            "course/create.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_CREATE_COURSE,)
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
        require_capabilities=(UserAuthorityCapabilityKeys.CAN_CREATE_COURSE,)
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
    ) -> HttpResponse:
        form = CreateCourseForm(organization, request.POST)
        if not form.is_valid():
            return cls._view(request, user_authority, organization, form=form)

        name = form.cleaned_data["name"]
        data = CourseCreateData(
            name=name,
            title=form.cleaned_data["title"],
            body=form.cleaned_data["body"],
            is_registerable=form.cleaned_data["is_registerable"],
            begins_at=form.cleaned_data["exercise_default_begins_at"],
            opens_at=form.cleaned_data["exercise_default_opens_at"],
            checks_at=form.cleaned_data["exercise_default_checks_at"],
            closes_at=form.cleaned_data["exercise_default_closes_at"],
            ends_at=form.cleaned_data["exercise_default_ends_at"],
            is_shared_after_confirmed=form.cleaned_data[
                "exercise_default_is_shared_after_confirmed"
            ],
            score_visible_from=form.cleaned_data["exercise_default_score_visible_from"],
            remarks_visible_from=form.cleaned_data[
                "exercise_default_remarks_visible_from"
            ],
        )
        create_course(data, organization, get_request_user_safe(request))

        return redirect("course/top", o_name=organization.name, c_name=name)
