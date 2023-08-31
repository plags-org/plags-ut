import traceback

from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_judge.core.parameter_decoder import get_exercise_concrete_identity_from_request
from app_judge.models import Submission


def _get(request, *_args, **_kwargs):
    """behavior against GET"""
    try:
        exercise_concrete_identity = get_exercise_concrete_identity_from_request(
            request.GET
        )

        submission_id = request.GET["submission_id"]
        submission = Submission.objects.get(id=submission_id)
        assert submission.agency_name == exercise_concrete_identity["agency_name"]
        assert (
            submission.agency_department_name
            == exercise_concrete_identity["agency_department_name"]
        )
        assert (
            submission.exercise_concrete_name
            == exercise_concrete_identity["exercise_concrete_name"]
        )
        assert (
            submission.exercise_concrete_version
            == exercise_concrete_identity["exercise_concrete_version"]
        )
        assert (
            submission.exercise_concrete_directory_hash
            == exercise_concrete_identity["exercise_concrete_directory_hash"]
        )

        # prepare return json
        return_info = {"evaluation_result_json": submission.evaluation_result_json}
        return JsonResponse(return_info)

    except AssertionError as exc:
        traceback.print_exc()
        raise Http404() from exc

    except Exception as exc:  # pylint: disable=broad-except
        traceback.print_exc()
        raise Http404() from exc

    raise Http404()


@csrf_exempt
def api_submission_result(request, *args, **kwargs):
    if request.method == "GET":
        return _get(request, *args, **kwargs)
    raise Http404()
