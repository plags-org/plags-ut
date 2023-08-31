from django.http.response import Http404
from django.shortcuts import render

from app_front.utils.auth_util import check_and_notify_exception


@check_and_notify_exception
def _get(request, *args, **kwargs):
    return render(request, "accounts/loggedout.html")


def view_accounts_loggedout(request, *args, **kwargs):
    if request.method == "GET":
        return _get(request, *args, **kwargs)
    raise Http404()
