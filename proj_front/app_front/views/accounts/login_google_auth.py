import contextlib
import random
from typing import ClassVar, Literal, Optional

from django.conf import settings
from django.contrib.auth import login
from django.db import IntegrityError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.translation import gettext_lazy as _
from google.auth.transport import requests
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials

from app_front.config.config import APP_CONFIG
from app_front.core.abs_view.google_oauth_view import AbsGoogleOauthView
from app_front.core.plags_utils.plags_endpoint import annotate_view_endpoint
from app_front.models import User


class LoginGoogleAuthView(AbsGoogleOauthView):
    _GOOGLE_OAUTH_CONFIG = APP_CONFIG.GOOGLE_AUTH
    _SCOPES = [
        # cf. <https://developers.google.com/identity/protocols/oauth2/scopes#oauth2>
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "openid",
        # 将来?
        # "https://www.googleapis.com/auth/drive.metadata.readonly",
    ]
    _HOSTED_DOMAIN = APP_CONFIG.GOOGLE_AUTH.hosted_domain
    _ACCESS_TYPE: ClassVar[Literal["offline"]] = "offline"
    _OAUTH_REDIRECT_PAGE_NAME = "login_google_auth"
    _ERROR_REDIRECT_PAGE_NAME = "profile"

    @classmethod
    @annotate_view_endpoint(require_login=False)
    def _get(cls, request: HttpRequest) -> HttpResponse:
        return cls._get_authorization(request)

    @classmethod
    def _pre_consent_hook(cls, request: HttpRequest) -> None:
        next_uri_path = request.GET.get("next")
        # for DEBUG
        # print(f"{next_uri_path=}")
        if next_uri_path is not None:
            request.session["google_auth_next_url"] = next_uri_path

    @classmethod
    def _handle_credentials(
        cls, request: HttpRequest, credentials: Credentials
    ) -> HttpResponse:
        # cf. <https://developers.google.com/identity/sign-in/web/backend-auth>

        # Google OAuth トークンの検証
        # for DEBUG
        # print(f"{credentials.id_token=}")
        google_id_info = id_token.verify_oauth2_token(
            credentials.id_token, requests.Request(), cls._GOOGLE_OAUTH_CONFIG.client_id
        )

        # Google ID トークンから必要な情報を抜き出す
        # cf. <https://developers.google.com/identity/protocols/oauth2/openid-connect>
        google_id_info_sub = google_id_info["sub"]
        google_id_info_email: str = google_id_info["email"]
        # NOTE name is not always available, but we require it because we use it as initial full_name
        google_id_info_name: str = google_id_info["name"]
        # KNOWLEDGE picture is not always available
        google_id_info_picture: Optional[str] = google_id_info.get("picture")

        # for DEBUG
        # print(f"{google_id_info=}")
        # print(f"{google_id_info_sub=}")

        if not google_id_info["email_verified"]:
            return cls._respond_with_error(request, _("Email is not verified."))
        if not google_id_info_email.endswith("@" + cls._HOSTED_DOMAIN):
            return cls._respond_with_error(
                request, _("Specified Google account is not of allowed domain.")
            )

        # Google ユーザーを PLAGS UT ユーザーとして認証する
        google_user: Optional[User] = None
        with contextlib.suppress(User.DoesNotExist):
            google_user = User.objects.get(google_id_info_sub=google_id_info_sub)

        if google_user is None:
            # PLAGS UT ユーザーが存在しなければ作成する
            num_random_digit = 7
            random_integer = random.randint(0, 10**num_random_digit - 1)
            while True:
                temporary_username = "user_" + f"{random_integer:0{num_random_digit}d}"
                print(f"{temporary_username=}")
                try:
                    google_user = User.objects.create(
                        username=temporary_username,  # 初期値埋め
                        # email=activate_input.email,
                        full_name=google_id_info_name,  # 初期値埋め
                        # student_card_number=transitory_user.student_card_number,
                        is_faculty=False,
                        invited_by=None,
                        activated_at=None,
                        timezone=settings.TIME_ZONE,
                        google_id_info_sub=google_id_info_sub,
                        google_id_info_email=google_id_info_email,
                        google_id_info_name=google_id_info_name,
                        google_id_info_picture=google_id_info_picture,
                    )
                    break
                except IntegrityError:
                    random_integer += 1

        # force-login
        # cf. <https://stackoverflow.com/questions/2787650/manually-logging-in-a-user-without-password> # noqa:E501
        login(request, google_user)

        next_uri_path: Optional[str] = request.session.get("google_auth_next_url")
        # for DEBUG
        # print(f"{next_uri_path=}")

        return redirect(next_uri_path or "profile")
