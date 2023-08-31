import traceback
from typing import Final, List, Tuple

from django.contrib import messages
from django.contrib.messages.constants import SUCCESS, WARNING
from django.db import IntegrityError, transaction
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render

from app_front.core.oc_user import get_sorted_course_users
from app_front.core.plags_utils.plags_endpoint import (
    AbsPlagsView,
    annotate_view_endpoint,
)
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import MetaOCKickoutUsersForm
from app_front.models import Course, CourseUser, Organization, User
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.exception_util import SystemResponsibleException
from app_front.utils.time_util import get_current_datetime

MessageLevel = int


class CourseUserKickoutView(AbsPlagsView):
    MANIPULATE_ACTION: Final[str] = "Kickout"
    MANIPULATE_DESCRIPTION: Final[str] = "Kickout users in"

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
        *,
        form: MetaOCKickoutUsersForm = None,
    ) -> HttpResponse:
        course_users = get_sorted_course_users(course)
        if form is None:
            form = MetaOCKickoutUsersForm()
        return render(
            request,
            "meta_oc/manipulate_user.html",
            dict(
                user_authority=user_authority,
                organization=organization,
                course=course,
                meta_oc_manipulate_action=cls.MANIPULATE_ACTION,
                meta_oc_manipulate_description=cls.MANIPULATE_DESCRIPTION,
                meta_oc_type="course",
                meta_oc=course,
                meta_oc_users=course_users,
                form=form,
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_COURSE_USER
    )
    def _get(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        return cls._view(request, user_authority, organization, course)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.CAN_MANAGE_COURSE_USER
    )
    def _post(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        organization: Organization,
        course: Course,
    ) -> HttpResponse:
        form = MetaOCKickoutUsersForm(request.POST)
        if not form.is_valid():
            return cls._view(request, user_authority, organization, course, form=form)

        clean_usernames = form.cleaned_data["clean_usernames"]
        try:
            message_list: List[Tuple[MessageLevel, str]] = []
            with transaction.atomic():
                for username in clean_usernames:
                    try:
                        user = User.objects.get(username=username)
                        course_user = CourseUser.objects.get(course=course, user=user)
                    except User.DoesNotExist:
                        message_list.append(
                            (WARNING, f"User [{username}] does not exist.")
                        )
                        continue
                    except CourseUser.DoesNotExist:
                        message_list.append(
                            (
                                WARNING,
                                f"User [{username}] is not a member of course [{course.name}].",
                            )
                        )
                        continue

                    course_user.is_active = False
                    course_user.is_active_updated_at = get_current_datetime()
                    course_user.is_active_updated_by = request.user
                    course_user.save()

                    message_list.append(
                        (
                            SUCCESS,
                            f"User [{username}] kicked out from course [{course.name}]",
                        )
                    )

        except IntegrityError as exc:
            SLACK_NOTIFIER.error(
                "Issue: course_user/kickout failed with IntegrityError",
                traceback.format_exc(),
            )
            traceback.print_exc()
            raise SystemResponsibleException(exc) from exc

        except Exception as exc:  # pylint: disable=broad-except
            SLACK_NOTIFIER.error(
                "Issue: course_user/kickout failed unexpectedly", traceback.format_exc()
            )
            traceback.print_exc()
            raise SystemResponsibleException(exc) from exc

        for level, message in message_list:
            messages.add_message(request, level, message)

        return redirect(
            "course_user/kickout", o_name=organization.name, c_name=course.name
        )
