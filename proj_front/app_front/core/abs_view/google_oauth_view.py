"""
Google OAuth 2.0 同意画面
"""
import abc
from typing import ClassVar, List, Optional

import oauthlib.oauth2.rfc6749.errors
from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from app_front.config.config_model import AppGoogleOauthConfig
from app_front.core.plags_utils.plags_endpoint import AbsPlagsView
from app_front.core.types import GoogleOauthAccessType, MailHostName


class AbsGoogleOauthView(AbsPlagsView):
    _GOOGLE_OAUTH_CONFIG: ClassVar[AppGoogleOauthConfig]
    _SCOPES: ClassVar[List[str]]
    _HOSTED_DOMAIN: ClassVar[Optional[MailHostName]]
    _ACCESS_TYPE: ClassVar[GoogleOauthAccessType]
    _OAUTH_REDIRECT_PAGE_NAME: ClassVar[str]
    _ERROR_REDIRECT_PAGE_NAME: ClassVar[str]

    @classmethod
    def _get_authorization(cls, request: HttpRequest) -> HttpResponse:
        if "state" not in request.GET:
            # 同意画面を返す
            return cls._get_consent(request)
        # 認証のリダイレクトを受けとり処理する
        return cls._handle_redirection(request)

    @classmethod
    def _build_redirect_uri(cls, request: HttpRequest) -> str:
        protocol_domain = f"{request.scheme}://{request.get_host()}"
        redirect_url = protocol_domain + reverse(cls._OAUTH_REDIRECT_PAGE_NAME)
        return redirect_url

    @classmethod
    def _respond_with_error(
        cls, request: HttpRequest, error_message: str
    ) -> HttpResponse:
        messages.error(request, error_message)
        return redirect(cls._ERROR_REDIRECT_PAGE_NAME)

    # NOTE 以下実装は以下参考資料に従ったものである
    # cf. <https://developers.google.com/identity/protocols/oauth2/web-server#python>

    @classmethod
    def _get_consent(cls, request: HttpRequest) -> HttpResponse:
        # Step 1: Set authorization parameters
        flow = Flow.from_client_secrets_file(
            cls._GOOGLE_OAUTH_CONFIG.client_secrets_file, scopes=cls._SCOPES
        )
        flow.redirect_uri = cls._build_redirect_uri(request)
        authorization_url, state = flow.authorization_url(
            # Enable offline access so that you can refresh an access token without
            # re-prompting the user for permission. Recommended for web server apps.
            access_type=cls._ACCESS_TYPE,
            # Enable incremental authorization. Recommended as a best practice.
            include_granted_scopes="true",
            # Enable hosted domain declaration
            hd=cls._HOSTED_DOMAIN,
        )

        # for DEBUG
        # print(f"{authorization_url=}")
        # print(f"{state=}")

        # session に必要情報を保持
        request.session["google_auth_state"] = state

        # 同意画面を応答する直前への処理挿入
        # e.g. URL のクエリをセッションに保持する
        cls._pre_consent_hook(request)

        # Step 2: Redirect to Google's OAuth 2.0 server
        return redirect(authorization_url)

    @classmethod
    def _pre_consent_hook(cls, request: HttpRequest) -> None:
        pass

    # NOTE 以下は client-side で行われる
    # Step 3: Google prompts user for consent
    # Step 4: Handle the OAuth 2.0 server response

    @classmethod
    def _handle_redirection(cls, request: HttpRequest) -> HttpResponse:
        # Step 5: Exchange authorization code for refresh and access tokens

        # Specify the state when creating the flow in the callback so that it can
        # verified in the authorization server response.
        state = request.session["google_auth_state"]
        flow = Flow.from_client_secrets_file(
            cls._GOOGLE_OAUTH_CONFIG.client_secrets_file,
            scopes=cls._SCOPES,
            state=state,
        )
        flow.redirect_uri = cls._build_redirect_uri(request)

        # Use the authorization server's response to fetch the OAuth 2.0 tokens.
        authorization_response = request.get_raw_uri()

        # ATTENTION HTTPS でないと Google が Insecure だと怒るが、ローカルだと HTTP なので誤魔化す
        if settings.IS_LOCAL:
            if authorization_response.startswith("http://localhost"):
                authorization_response = authorization_response.replace(
                    "http://localhost", "https://localhost", 1
                )

        # for DEBUG
        # print(f"{authorization_response=}")
        try:
            flow.fetch_token(authorization_response=authorization_response)
        except Warning as exc_warning:
            if exc_warning.args[0].startswith("Scope has changed from"):
                return cls._respond_with_error(
                    request, _("Authentication canceled (Scope changed)")
                )
            raise
        except oauthlib.oauth2.rfc6749.errors.AccessDeniedError:
            return cls._respond_with_error(
                request, _("Authentication canceled (Access Denied)")
            )
        except oauthlib.oauth2.rfc6749.errors.InvalidGrantError:
            return cls._respond_with_error(
                request, _("Authenticated with insufficient authority")
            )

        return cls._handle_credentials(request, flow.credentials)

    @classmethod
    @abc.abstractmethod
    def _handle_credentials(
        cls, request: HttpRequest, credentials: Credentials
    ) -> HttpResponse:
        """同意された認証情報を処理し応答する"""
        raise NotImplementedError
