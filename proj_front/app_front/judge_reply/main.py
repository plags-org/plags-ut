import json
import logging
from typing import Optional

from django.http import Http404, HttpResponseBadRequest
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from pydantic import BaseModel, ValidationError

from app_front.config.config import APP_CONFIG
from app_front.core.judge_util import save_submission_evaluation_result_json
from app_front.models import Submission


class _RequestData(BaseModel):
    submission_id: int
    token: str
    progress: int
    # 評価完了時（progress = 100）にのみ付属する
    evaluation_result_json: Optional[str] = None


@csrf_exempt
def judge_reply_main(request: HttpRequest) -> HttpResponse:
    if request.method != "POST":
        raise Http404

    try:
        request_data = _RequestData.parse_raw(request.body)
    except (json.JSONDecodeError, ValidationError):
        logging.exception("parse failed")
        return HttpResponseBadRequest("invalid body")

    # token で認証
    if request_data.token != APP_CONFIG.JUDGE.API_TOKEN:
        return HttpResponseBadRequest("invalid token")

    try:
        submission = Submission.objects.get(id=request_data.submission_id)
    except Submission.DoesNotExist:
        logging.exception("submission not found")
        return HttpResponseBadRequest(
            "submission not found: " + repr(request_data.submission_id)
        )

    # submission を更新
    submission.evaluation_progress_percent = request_data.progress

    if request_data.progress == 100:
        assert request_data.evaluation_result_json is not None
        save_submission_evaluation_result_json(
            submission, request_data.evaluation_result_json
        )

    submission.save()

    return HttpResponse(content="OK")
