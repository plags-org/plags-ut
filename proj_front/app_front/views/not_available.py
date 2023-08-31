from django.contrib.auth.decorators import login_required
from django.http.response import Http404
from django.shortcuts import render

from app_front.utils.auth_util import check_and_notify_exception


@login_required
@check_and_notify_exception
def _get(request, *args, **kwargs):
    return render(request, "not_available.html")


def view_not_available(request, *args, **kwargs):
    if request.method == "GET":
        return _get(request, *args, **kwargs)
    raise Http404()
