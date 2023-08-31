from django.contrib.auth.decorators import login_required
from pydantic import BaseModel

from app_front.core.api_decorator import ApiErrorData, ApiException, api_post
from app_front.core.course import is_course_visible_to_user_authority
from app_front.models import Course
from app_front.utils.auth_util import (
    RequestContext,
    annex_context,
    check_and_notify_api_exception,
)


class RequestData(BaseModel):
    pass


class ResponseData(BaseModel):
    description_markdown: str


LOCATION = ["course.get"]


@login_required
@annex_context
@check_and_notify_api_exception
@api_post(RequestData)
def api_course_get(context: RequestContext, data: RequestData) -> ResponseData:
    try:
        if not is_course_visible_to_user_authority(
            context.course, context.user_authority
        ):
            raise ApiException(
                ApiErrorData(
                    loc=LOCATION,
                    msg="No view authority on specified Course (Not published)",
                    type="Course.NoViewAuthority",
                )
            )
        return ResponseData(
            description_markdown=context.course.body,
        )
    except Course.DoesNotExist as exc:
        raise ApiException(
            ApiErrorData(
                loc=LOCATION,
                msg="Specified Course does not exist",
                type="Course.DoesNotExist",
            )
        ) from exc
