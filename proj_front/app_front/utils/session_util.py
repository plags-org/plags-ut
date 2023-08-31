"""
セッション情報の管理すべてを担当する。

書き込みはすべてこれを通して行うこと。
（読み込みについては、templateのこともあるので強制はしない。）

データ構造：
request.session = dict(
    authority_cache = dict(
        organizations = dict(
            {o_name} = {authority_level}
            ...
        ),
        courses = dict(
            {o_name} = dict(
                {c_name} = {authority_level}
                ...
            ),
            ...
        ),
        timeouts_at = float({timestamp}),
    ),
)
"""
import traceback
from functools import wraps

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver
from django.utils import timezone

from app_front.models import CourseUser, LoginHistory, OrganizationUser
from app_front.utils.alert_util import SLACK_NOTIFIER

KEY_AUTHORITY_CACHE = "authority_cache"

KEY_ORGANIZATIONS = "organizations"
KEY_COURSES = "courses"
KEY_TIMEOUTS_AT = "timeouts_at"


def get_session_expiry():
    # とりあえず3時間
    return 60 * 60 * 3


def is_authority_cached(request):
    if KEY_AUTHORITY_CACHE in request.session:
        if request.session[KEY_AUTHORITY_CACHE][KEY_TIMEOUTS_AT] < timezone.now():
            return True
    return False


def get_authority_cache_timeouts_at():
    # とりあえず30分間
    return timezone.now().timestamp() + 60 * 30


def get_authority_cache(request):
    ones_organizations = OrganizationUser.objects.filter(user=request.user)
    ones_courses = CourseUser.objects.filter(user=request.user)

    organizations = {ou.organization.name: ou.authority for ou in ones_organizations}
    courses = {}
    for cu in ones_courses:
        courses.setdefault(cu.course.organization.name, {})
        courses[cu.course.organization.name][cu.course.name] = cu.authority

    authority_cache = {
        KEY_ORGANIZATIONS: organizations,
        KEY_COURSES: courses,
        KEY_TIMEOUTS_AT: get_authority_cache_timeouts_at(),
    }
    return authority_cache


def session_cache_authority():
    """
    Decorator for views that checks that the user have enough authority to do some action.
    If it is not enough, redirects to the log-in page.
    The test should be a callable that takes the user object, *args and **kwargs,
    then returns True if the user have enough authority.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # update expiry
            request.session.set_expiry(get_session_expiry())

            # go through if already cached
            if is_authority_cached(request):
                return view_func(request, *args, **kwargs)

            # get authority cache
            authority_cache = get_authority_cache(request)
            request.session[KEY_AUTHORITY_CACHE] = authority_cache

            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


@receiver(user_logged_in)
def user_logged_in_callback(_sender, request, user, **_kwargs):
    LoginHistory.objects.create(user=user, session_key=request.session.session_key)


@receiver(user_logged_out)
def user_logged_out_callback(_sender, request, user, **_kwargs):
    login_history = LoginHistory.objects.filter(
        user=user, session_key=request.session.session_key, logged_out_at__isnull=True
    )
    if not login_history:
        message = (
            f"On: {request.build_absolute_uri()}\n"
            f"By: {request.user.username}\n"
            f"Params: {user=}, {request.session.session_key=}\n"
            f"Issue: Detected Unexpected Record Condition"
        )
        SLACK_NOTIFIER.error(message, tracebacks=traceback.format_exc())
        return

    latest_login_history = login_history.latest("pk")
    latest_login_history.logged_out_at = timezone.now()
    latest_login_history.save()
