from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from app_front.core.system_settings import get_system_settings
from app_front.forms import AdministrationSystemSettingsForm
from app_front.utils.auth_util import annex_user_authority, check_and_notify_exception
from app_front.utils.time_util import get_current_datetime


def _render_request(
    request, user_authority, form: AdministrationSystemSettingsForm = None
):
    system_settings = get_system_settings()

    if form is None:
        form = AdministrationSystemSettingsForm(
            initial=dict(
                use_login_page_notice=system_settings.use_login_page_notice,
                login_page_notice_title=system_settings.login_page_notice_title,
                login_page_notice_text=system_settings.login_page_notice_text,
            )
        )

    return render(
        request,
        "administration/system_settings.html",
        dict(
            user_authority=user_authority,
            system_settings=system_settings,
            form=form,
        ),
    )


@login_required
@check_and_notify_exception
@annex_user_authority
def _get(request, user_authority, *_args, **_kwargs):
    return _render_request(request, user_authority)


@login_required
@check_and_notify_exception
@annex_user_authority
def _post(request, user_authority, *_args, **_kwargs):
    form = AdministrationSystemSettingsForm(request.POST)

    if not form.is_valid():
        messages.warning(request, "Invalid input.")
        return _render_request(request, user_authority, form)

    # Parse / Validation
    use_login_page_notice = form.cleaned_data["use_login_page_notice"]
    login_page_notice_title = form.cleaned_data["login_page_notice_title"]
    login_page_notice_text = form.cleaned_data["login_page_notice_text"]

    current_datetime = get_current_datetime()

    # Update
    system_settings = get_system_settings()

    if system_settings.use_login_page_notice != use_login_page_notice:
        system_settings.use_login_page_notice = use_login_page_notice
        system_settings.use_login_page_notice_updated_at = current_datetime
        system_settings.use_login_page_notice_updated_by = request.user

    current_content = (
        system_settings.login_page_notice_title,
        system_settings.login_page_notice_text,
    )
    updating_content = (
        login_page_notice_title,
        login_page_notice_text,
    )
    if current_content != updating_content:
        system_settings.login_page_notice_title = login_page_notice_title
        system_settings.login_page_notice_text = login_page_notice_text
        system_settings.login_page_notice_content_updated_at = current_datetime
        system_settings.login_page_notice_content_updated_by = request.user

    system_settings.save()

    messages.info(request, "System settings update successful.")
    return redirect("administration/system_settings")


def view_administration_system_settings(request, *args, **kwargs):
    if request.method == "POST":
        return _post(request, *args, **kwargs)
    return _get(request, *args, **kwargs)
