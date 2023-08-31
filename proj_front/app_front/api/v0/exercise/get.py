from django.contrib.auth.decorators import login_required
from pydantic import BaseModel

from app_front.core.api_decorator import ApiErrorData, ApiException, api_post
from app_front.core.exercise import is_exercise_visible_to_user_authority
from app_front.models import Exercise
from app_front.utils.auth_util import (
    RequestContext,
    annex_context,
    check_and_notify_api_exception,
)


class RequestData(BaseModel):
    name: str


class ResponseData(BaseModel):
    body_ipynb_json: str


LOCATION = ["exercise.get"]


@login_required
@annex_context
@check_and_notify_api_exception
@api_post(RequestData)
def api_exercise_get(context: RequestContext, data: RequestData) -> ResponseData:
    try:
        exercise: Exercise = Exercise.objects.get(course=context.course, name=data.name)
        if not is_exercise_visible_to_user_authority(exercise, context.user_authority):
            raise ApiException(
                ApiErrorData(
                    loc=LOCATION,
                    msg="No view authority on specified Exercise (Not published)",
                    type="Exercise.NoViewAuthority",
                )
            )
        return ResponseData(
            body_ipynb_json=exercise.body_ipynb_json,
        )
    except Exercise.DoesNotExist as exc:
        raise ApiException(
            ApiErrorData(
                loc=LOCATION,
                msg="Specified Exercise does not exist",
                type="Exercise.DoesNotExist",
            )
        ) from exc
