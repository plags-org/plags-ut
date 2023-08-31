import dataclasses
import traceback
from typing import Any

from django.conf import settings
from django.http import Http404, JsonResponse
from django.http.request import HttpRequest
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from app_judge.core.evaluator import EvaluationInfo, evaluation_func, submission_queue
from app_judge.core.parameter_decoder import get_exercise_concrete_identity_from_request
from app_judge.core.version import JUDGE_CORE_API_VERSION
from app_judge.models import Submission


def _post(request: HttpRequest, *_args: Any, **_kwargs: Any) -> JsonResponse:
    """behavior against POST"""
    try:
        # validate submission
        exercise_concrete_identity = get_exercise_concrete_identity_from_request(
            request.POST
        )

        assert "submission_id" in request.POST
        print(repr(request.POST["submission_id"]))
        front_submission_id = int(request.POST["submission_id"])

        assert "submission_file" in request.FILES
        submission_file = request.FILES["submission_file"]

        # create additional data
        submitted_host_ip = request.META["REMOTE_ADDR"]
        submitted_host = request.META["REMOTE_HOST"]
        submitted_at = timezone.now()
        api_version = JUDGE_CORE_API_VERSION

        assert request.POST["token"] == settings.JUDGE_API_TOKEN

        # copy submission info
        submission_kwargs = dict(
            **exercise_concrete_identity,
            front_submission_id=front_submission_id,
            submitted_host_ip=submitted_host_ip,
            submitted_host=submitted_host,
            submitted_at=submitted_at,
            api_version=api_version,
        )

        # id を確定させてから、その id のディレクトリにファイルを保存
        submission = Submission.objects.create(**submission_kwargs)
        submission.submission_file = submission_file
        submission.save()

        # enqueue evaluation job
        evaluation_info = EvaluationInfo(
            **exercise_concrete_identity,
            submission_id=submission.id,
            submission_file_name=submission.submission_file.name,
        )
        evaluation_job = submission_queue.enqueue(evaluation_func, evaluation_info)
        print(
            "[DEBUG]",
            "<evaluation_job_uuid>",
            evaluation_job.get_id(),
            ", <evaluation_info>",
            evaluation_info,
        )

        return JsonResponse(dataclasses.asdict(evaluation_info))

    except AssertionError as exc:
        traceback.print_exc()
        raise Http404() from exc

    except Exception as exc:  # pylint: disable=broad-except
        traceback.print_exc()
        raise Http404() from exc

    raise Http404()


@csrf_exempt
def api_submission_submit(
    request: HttpRequest, *args: Any, **kwargs: Any  # type:ignore[misc]
) -> JsonResponse:
    if request.method == "POST":
        return _post(request, *args, **kwargs)
    raise Http404()
