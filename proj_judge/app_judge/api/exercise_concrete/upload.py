import os
import tempfile
import traceback
import zipfile
from typing import Any

from django.http import Http404, JsonResponse
from django.http.request import HttpRequest
from django.views.decorators.csrf import csrf_exempt

from app_judge.core.evaluator import (
    get_exercise_concrete_base_dir,
    get_exercise_concrete_dir,
    is_exercise_concrete_exists,
)
from app_judge.core.parameter_decoder import get_exercise_concrete_identity_from_request
from judge_core.exercise_concrete.common.schema_util import SettingValidationError
from judge_core.exercise_concrete.exercise_loader import load_exercise_concrete


def _post(request: HttpRequest, *_args: Any, **_kwargs: Any) -> JsonResponse:
    try:
        assert "exercise_concrete_zip_file" in request.FILES

        exercise_concrete_identity = get_exercise_concrete_identity_from_request(
            request.POST
        )
        if is_exercise_concrete_exists(**exercise_concrete_identity):
            return JsonResponse({"success": False, "reasons": ["Already exists"]})

        exercise_concrete_zip_file = request.FILES["exercise_concrete_zip_file"]
        exercise_concrete_base_dir = get_exercise_concrete_base_dir(
            **exercise_concrete_identity
        )
        os.makedirs(exercise_concrete_base_dir, exist_ok=True)
        exercise_concrete_zip_path = os.path.join(
            exercise_concrete_base_dir, "uploaded.zip"
        )
        with open(exercise_concrete_zip_path, "wb") as zip_f:
            zip_f.write(exercise_concrete_zip_file.read())

        # /tmp に展開して settings.json などのバリデーション
        tmp_exercise_concrete_dir = tempfile.mkdtemp("plags_ut_judge")
        print(tmp_exercise_concrete_dir)
        with zipfile.ZipFile(exercise_concrete_zip_path) as z_ipf:
            z_ipf.extractall(tmp_exercise_concrete_dir)

        # バリデーション
        try:
            setting_json_path = os.path.join(tmp_exercise_concrete_dir, "setting.json")
            if not os.path.isfile(setting_json_path):
                return JsonResponse(
                    {"success": False, "reasons": ["setting.json not found"]}
                )
            _ = load_exercise_concrete(tmp_exercise_concrete_dir)
            print(_)
        except SettingValidationError as exc:
            return JsonResponse({"success": False, "reasons": [exc.args[0]]})
        except Exception:  # pylint:disable=broad-except
            traceback.print_exc()
            return JsonResponse({"success": False, "reasons": ["unexpected exception"]})

        # バリデーションを通過したので設置
        exercise_concrete_dir = get_exercise_concrete_dir(**exercise_concrete_identity)
        with zipfile.ZipFile(exercise_concrete_zip_path) as z_ipf:
            z_ipf.extractall(exercise_concrete_dir)

        return JsonResponse({"success": True})

    except AssertionError as exc:
        traceback.print_exc()
        raise Http404() from exc

    except Exception as exc:  # pylint: disable=broad-except
        traceback.print_exc()
        raise Http404() from exc


@csrf_exempt
def api_exercise_concrete_upload(request, *args, **kwargs):
    if request.method == "POST":
        return _post(request, *args, **kwargs)
    raise Http404()
