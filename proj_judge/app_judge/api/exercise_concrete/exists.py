import traceback
from typing import Any

from django.http import Http404, JsonResponse
from django.http.request import HttpRequest
from django.views.decorators.csrf import csrf_exempt

# from app_judge.models import Agency
from app_judge.core.evaluator import is_exercise_concrete_exists
from app_judge.core.parameter_decoder import get_exercise_concrete_identity_from_request


def _get(request: HttpRequest, *_args: Any, **_kwargs: Any) -> JsonResponse:
    try:
        exercise_concrete_identity = get_exercise_concrete_identity_from_request(
            request.GET
        )
        exists = is_exercise_concrete_exists(**exercise_concrete_identity)
        return JsonResponse(
            {
                "result": {
                    "identity": exercise_concrete_identity,
                    "exists": exists,
                }
            }
        )

    except AssertionError as exc:
        traceback.print_exc()
        raise Http404() from exc

    except Exception as exc:  # pylint: disable=broad-except
        traceback.print_exc()
        raise Http404() from exc

    raise Http404()


@csrf_exempt
def api_exercise_concrete_exists(
    request: HttpRequest, *args: Any, **kwargs: Any
) -> JsonResponse:
    if request.method == "GET":
        return _get(request, *args, **kwargs)
    # if request.method == 'POST':
    #     return _post(request, *args, **kwargs)
    raise Http404()
