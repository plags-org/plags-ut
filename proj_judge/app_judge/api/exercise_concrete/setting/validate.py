from django.http import Http404
from django.views.decorators.csrf import csrf_exempt

# from app_judge.models import Agency, Submission


def _get(request, *_args, **_kwargs):
    pass


def _post(request, *_args, **_kwargs):
    pass


@csrf_exempt
def api_exercise_concrete_setting_validate(request, *args, **kwargs):
    if request.method == "GET":
        return _get(request, *args, **kwargs)
    if request.method == "POST":
        return _post(request, *args, **kwargs)
    raise Http404()
