from django.contrib.auth.signals import (  # , user_login_failed
    user_logged_in,
    user_logged_out,
)
from django.dispatch import receiver

from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import LoginHistory
from app_front.utils.time_util import get_current_datetime


@receiver(user_logged_in)
def user_logged_in_callback(sender, request, user, **kwargs):
    del sender, kwargs
    ip_address = request.META.get("REMOTE_ADDR")
    LoginHistory.objects.create(
        user=user,
        ip_address=ip_address,
        session_key=request.session.session_key,
    )


@receiver(user_logged_out)
def user_logged_out_callback(sender, request, user, **kwargs):
    del sender, kwargs
    session_key = request.session.session_key
    history = (
        LoginHistory.objects.filter(session_key=session_key)
        .order_by("-logged_in_at")
        .first()
    )
    if history is None:
        SLACK_NOTIFIER.error(f"No corresponding session history: {session_key=}")
        return
    if history.user != user:
        # if user is None:
        #     return
        SLACK_NOTIFIER.error(
            f"History and real user mismatch: {session_key=}, {history.user.username=} != {user.username=}"
        )
        return
    history.logged_out_at = get_current_datetime()
    history.save()


# @receiver(user_login_failed)
# def user_login_failed_callback(sender, credentials, **kwargs):
#     pass
