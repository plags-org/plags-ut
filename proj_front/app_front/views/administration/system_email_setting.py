import traceback
from typing import ClassVar, Dict, Literal, Optional

from django.contrib import messages
from django.http import Http404
from django.http.request import HttpRequest
from django.http.response import HttpResponse
from django.shortcuts import redirect, render
from google.auth.transport import requests
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials
from pydantic import EmailStr, parse_obj_as

from app_front.config.config import APP_CONFIG
from app_front.core.abs_view.google_oauth_view import AbsGoogleOauthView
from app_front.core.plags_utils.plags_endpoint import annotate_view_endpoint
from app_front.core.plags_utils.request_user import get_request_user_safe
from app_front.core.system_settings import (
    get_system_mail_sender_data,
    get_system_settings,
    get_to_address_override_config,
)
from app_front.core.user import get_username_nullable
from app_front.forms import (
    AdministrationSystemEmailSendTestForm,
    AdministrationSystemEmailToAddressOverrideForm,
)
from app_front.utils.auth_util import UserAuthorityCapabilityKeys, UserAuthorityDict
from app_front.utils.email_util import (
    send_email_to_address,
    send_registered_as_system_email_sender_account_notification,
)
from app_front.utils.time_util import get_current_datetime

_SEND_TEST_EMAIL_OBJECTIVE = "Send test mail"


class AdministrationEmailSettingView(AbsGoogleOauthView):
    PAGE_NAME = "administration/system_email_setting"

    _GOOGLE_OAUTH_CONFIG = APP_CONFIG.SYSTEM_MAIL.GOOGLE_GMAIL_API
    _SCOPES = [
        # cf. <https://developers.google.com/identity/protocols/oauth2/scopes#oauth2>
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        "https://www.googleapis.com/auth/gmail.send",
        # 将来?
        # "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]
    _HOSTED_DOMAIN = None
    _ACCESS_TYPE: ClassVar[Literal["offline"]] = "offline"
    _OAUTH_REDIRECT_PAGE_NAME = PAGE_NAME
    _ERROR_REDIRECT_PAGE_NAME = PAGE_NAME

    @classmethod
    def _view(
        cls,
        request: HttpRequest,
        user_authority: UserAuthorityDict,
        *,
        email_send_test_form: Optional[AdministrationSystemEmailSendTestForm] = None,
        to_address_override_form: Optional[
            AdministrationSystemEmailToAddressOverrideForm
        ] = None,
    ) -> HttpResponse:
        if email_send_test_form is None:
            email_send_test_form = AdministrationSystemEmailSendTestForm()
        if to_address_override_form is None:
            to_address_override_form = AdministrationSystemEmailToAddressOverrideForm(
                initial=get_to_address_override_config().dict()
            )

        system_settings = get_system_settings()

        return render(
            request,
            "administration/system_email_setting.html",
            dict(
                user_authority=user_authority,
                target_user=request.user,
                email_send_test_form=email_send_test_form,
                to_address_override_form=to_address_override_form,
                email_sender_email=system_settings.email_sender_google_id_info_email,
                email_sender_name=system_settings.email_sender_google_id_info_name,
                email_sender_updated_at=system_settings.email_sender_updated_at,
                email_sender_updated_by=get_username_nullable(
                    system_settings.email_sender_updated_by
                ),
            ),
        )

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.IS_SUPERUSER
    )
    def _get(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        if any(kw in request.GET for kw in ("consent", "state")):
            return cls._get_authorization(request)

        return cls._view(request, user_authority)

    @classmethod
    def _handle_credentials(
        cls, request: HttpRequest, credentials: Credentials
    ) -> HttpResponse:
        """同意された認証情報を処理し応答する"""
        request_user = get_request_user_safe(request)

        system_settings = get_system_settings()

        google_id_info = id_token.verify_oauth2_token(
            credentials.id_token, requests.Request(), cls._GOOGLE_OAUTH_CONFIG.client_id
        )

        # NOTE 実際に利用できる認証情報であることを、実際にメールを送信して確認する
        # KNOWLEDGE 検証段階で一度、 `refresh_token` キーのない credentials が登録されてしまった。
        #           これを防止するために実装したが、その後事象を再現できないままである。
        # KNOWLEDGE おそらく「同じアカウントで複数回認証を行った場合」に発生すると思われる。
        sender_email = google_id_info["email"]
        credentials_json_str = credentials.to_json()
        protocol_domain = f"{request.scheme}://{request.get_host()}"
        result = send_registered_as_system_email_sender_account_notification(
            sender_email,
            credentials_json_str=credentials_json_str,
            protocol_domain=protocol_domain,
        )
        if not result.success:
            messages.error(
                request,
                "Update rejected: Failed to send email as the account specified.",
            )
            return redirect(cls.PAGE_NAME)

        system_settings.email_sender_google_id_info_sub = google_id_info["sub"]
        system_settings.email_sender_google_id_info_email = sender_email
        system_settings.email_sender_google_id_info_name = google_id_info["name"]
        system_settings.email_sender_google_id_info_picture = google_id_info["picture"]
        system_settings.email_sender_google_credentials_json_str = credentials_json_str
        system_settings.email_sender_updated_at = get_current_datetime()
        system_settings.email_sender_updated_by = request_user
        system_settings.save()

        messages.success(request, "Updated sender account.")
        return redirect(cls.PAGE_NAME)

    @classmethod
    @annotate_view_endpoint(
        require_capabilities=UserAuthorityCapabilityKeys.IS_SUPERUSER
    )
    def _post(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        if "clear_sender_account" in request.POST:
            return cls._post_clear_sender_account(request, user_authority)
        if "send_test_email" in request.POST:
            return cls._post_send_test_email(request, user_authority)
        if "to_address_override" in request.POST:
            return cls._post_to_address_override(request, user_authority)
        raise Http404

    @classmethod
    def _post_clear_sender_account(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        del user_authority
        request_user = get_request_user_safe(request)

        system_settings = get_system_settings()

        if system_settings.email_sender_google_credentials_json_str is not None:
            pass

        system_settings.email_sender_google_id_info_sub = None
        system_settings.email_sender_google_id_info_email = None
        system_settings.email_sender_google_id_info_name = None
        system_settings.email_sender_google_id_info_picture = None
        system_settings.email_sender_google_credentials_json_str = None
        system_settings.email_sender_updated_at = get_current_datetime()
        system_settings.email_sender_updated_by = request_user
        system_settings.save()

        messages.success(request, "Cleared sender account.")
        return redirect(cls.PAGE_NAME)

    @classmethod
    def _post_send_test_email(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        email_send_test_form = AdministrationSystemEmailSendTestForm(request.POST)
        if not email_send_test_form.is_valid():
            return cls._view(
                request, user_authority, email_send_test_form=email_send_test_form
            )

        system_mail_sender_data = get_system_mail_sender_data()
        if system_mail_sender_data is None:
            messages.error(
                request, "Send test mail failed: Please update sending account first"
            )
            return cls._view(
                request, user_authority, email_send_test_form=email_send_test_form
            )

        # Parse / Validation
        target = parse_obj_as(EmailStr, email_send_test_form.cleaned_data["target"])
        subject = email_send_test_form.cleaned_data["subject"]
        body_template = email_send_test_form.cleaned_data["body_template"]

        body_template_params: Dict[str, str] = dict(email=target)

        # Send email
        try:
            email_result = send_email_to_address(
                _SEND_TEST_EMAIL_OBJECTIVE,
                subject,
                body_template,
                target,
                body_template_params=body_template_params,
            )
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            messages.error(request, "Send test mail failed.")
        else:
            if email_result.success:
                messages.success(request, "Send test mail successful.")
            else:
                messages.error(request, "Send test mail failed.")

        return redirect(cls.PAGE_NAME)

    @classmethod
    def _post_to_address_override(
        cls, request: HttpRequest, user_authority: UserAuthorityDict
    ) -> HttpResponse:
        to_address_override_form = AdministrationSystemEmailToAddressOverrideForm(
            request.POST
        )
        if not to_address_override_form.is_valid():
            return cls._view(
                request,
                user_authority,
                to_address_override_form=to_address_override_form,
            )

        enabled = to_address_override_form.cleaned_data["enabled"]
        email = to_address_override_form.cleaned_data["email"]

        request_user = get_request_user_safe(request)
        system_settings = get_system_settings()

        if (enabled, email) == (
            system_settings.email_to_address_override_enabled,
            system_settings.email_to_address_override_email,
        ):
            messages.info(request, 'No change on "To" address override setting.')
            return redirect(cls.PAGE_NAME)

        try:
            system_settings.email_to_address_override_enabled = enabled
            system_settings.email_to_address_override_email = email
            system_settings.email_to_address_override_updated_at = (
                get_current_datetime()
            )
            system_settings.email_to_address_override_updated_by = request_user
            system_settings.save()

        except Exception:  # pylint:disable=broad-except
            messages.error(request, 'Failed to update "To" address override setting.')
            return cls._view(
                request,
                user_authority,
                to_address_override_form=to_address_override_form,
            )

        messages.success(request, 'Updated "To" address override setting.')
        return redirect(cls.PAGE_NAME)
