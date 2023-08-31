"""
See <https://developers.google.com/drive/api/v3/quickstart/python>

設定手順(新):

1. GCPのサービスアカウントを作成する
2. service_credentials.json を設置する

設定手順(旧):

1. <https://developers.google.com/workspace/guides/create-credentials#configure_the_oauth_consent_screen> の "Configure the OAuth consent screen" を実行
2. <https://developers.google.com/workspace/guides/create-credentials#web> の "Create Web application credentials (web server app)" を実行
3. 2. でダウンロードした secret credential の JSON を `CONFIG_DIR/google_drive/credentials.json` に配置
4. `./manage.py create_and_test_google_drive_credential` を実行
5. 「認証情報」ページ ( <https://console.cloud.google.com/apis/credentials?organizationId=0&project=${project_name}&supportedpurview=project> ?) から「OAuth 2.0 クライアント ID」の対応するキーの「編集」を押して、必要な「承認済みのリダイレクト URI」を追加
6. ログインして認証（ 裏で `CONFIG_DIR/google_drive/token.json` が作られる ）
7. <https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=${project_id}> にアクセスしてDriveAPIを追加
8. 動作確認
"""
import dataclasses
import io
import os
import traceback
from typing import List, Sequence

import googleapiclient.errors
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as ServiceCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.utils.exception_util import (
    SystemLogicalError,
    SystemResponsibleException,
)

from .notebook_util import get_file_from_google_drive_by_requests
from .types import GoogleDriveFileDownloadMethod
from .utils import get_max_file_size

# If modifying these scopes, delete the file token.json.
SCOPES = [
    "https://www.googleapis.com/auth/drive.metadata.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

TOKEN_JSON_FILENAME = "token.json"
CREDENTIALS_JSON_FILENAME = "credentials.json"
SERVICE_CREDENTIALS_JSON_FILENAME = "service_credentials.json"


class GoogleDriveApiMisConfigured(SystemResponsibleException):
    pass


def get_google_drive_config_dir() -> str:
    return os.path.join(settings.CONFIG_DIR, "google_drive")


def get_token(google_drive_config_dir: str) -> Credentials:
    token_filepath = os.path.join(google_drive_config_dir, TOKEN_JSON_FILENAME)
    token = None
    if os.path.exists(token_filepath):
        token = Credentials.from_authorized_user_file(token_filepath, SCOPES)
    # If there are no (valid) token available, let the user log in.
    if not token:
        raise GoogleDriveApiMisConfigured("No token")
    if not token.valid:
        raise GoogleDriveApiMisConfigured("Token not valid")
    return token


def get_or_refresh_token(google_drive_config_dir: str) -> Credentials:
    token_filepath = os.path.join(google_drive_config_dir, TOKEN_JSON_FILENAME)
    token = None
    if os.path.exists(token_filepath):
        token = Credentials.from_authorized_user_file(token_filepath, SCOPES)
    # If there are no (valid) token available, let the user log in.
    if not token or not token.valid:
        if token and token.expired and token.refresh_token:
            token.refresh(Request())
        else:
            raise ValueError("No token")
        # Save the token for the next run
        with open(token_filepath, "w", encoding="utf_8") as token_file:
            token_file.write(token.to_json())
    return token


def get_or_create_token(google_drive_config_dir: str) -> Credentials:
    credential_filepath = os.path.join(
        google_drive_config_dir, CREDENTIALS_JSON_FILENAME
    )
    token_filepath = os.path.join(google_drive_config_dir, TOKEN_JSON_FILENAME)
    token = None
    if os.path.exists(token_filepath):
        token = Credentials.from_authorized_user_file(token_filepath, SCOPES)
    # If there are no (valid) token available, let the user log in.
    if not token or not token.valid:
        if token and token.expired and token.refresh_token:
            token.refresh(Request())
        else:
            if not os.path.exists(credential_filepath):
                raise ValueError(
                    f"No {credential_filepath!r} file. Follow instructions on "
                    "<https://developers.google.com/workspace/guides/create-credentials#web>, "
                    '"Create Web application credentials (web server app)".'
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                credential_filepath, SCOPES
            )
            token = flow.run_local_server(port=0)
        # Save the token for the next run
        with open(token_filepath, "w", encoding="utf_8") as token_file:
            token_file.write(token.to_json())
    return token


def get_service_credentials(google_drive_config_dir: str) -> ServiceCredentials:
    credential_filepath = os.path.join(
        google_drive_config_dir, SERVICE_CREDENTIALS_JSON_FILENAME
    )
    if not os.path.exists(credential_filepath):
        raise GoogleDriveApiMisConfigured(
            f"Credential file {credential_filepath!r} not found"
        )
    return ServiceCredentials.from_service_account_file(credential_filepath)


@dataclasses.dataclass
class GoogleDriveFileData:
    name: str
    mime_type: str
    content: str


class GoogleDriveApiException(Exception):
    pass


class GoogleDriveResourceNotFound(GoogleDriveApiException):
    pass


class GoogleDriveResourceTooLarge(GoogleDriveApiException):
    pass


def get_file_from_google_drive_by_api(
    resource_id: str, *, token=None
) -> GoogleDriveFileData:
    # see <https://developers.google.com/drive/api/v3/manage-downloads#python>
    if token is None:
        token = get_token(get_google_drive_config_dir())
    drive_service = build("drive", "v3", credentials=token)

    try:
        file_metadata = (
            drive_service.files()
            .get(fileId=resource_id, fields="size, name, mimeType")
            .execute()
        )
        # e.g. {'name': 'pre1en.ipynb', 'mimeType': 'application/x-ipynb+json', 'size': '3791'}
        print(resource_id, file_metadata)
        if (file_size := int(file_metadata["size"])) >= (
            max_file_size := get_max_file_size()
        ):
            raise GoogleDriveResourceTooLarge(
                f"Notebook file too large: {file_size} >= {max_file_size}"
            )

        request = drive_service.files().get_media(fileId=resource_id)
        file_handler = io.BytesIO()
        downloader = MediaIoBaseDownload(file_handler, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print("Download %d%%." % int(status.progress() * 100))
    except googleapiclient.errors.HttpError as exc:
        raise GoogleDriveResourceNotFound(
            f"Failed to download resource {resource_id!r}"
        ) from exc

    return GoogleDriveFileData(
        name=file_metadata["name"],
        mime_type=file_metadata["mimeType"],
        content=str(file_handler.getvalue(), encoding="utf_8"),
    )


def get_file_from_google_drive_by_api_service_account(
    resource_id: str,
) -> GoogleDriveFileData:
    creds = get_service_credentials(get_google_drive_config_dir())
    return get_file_from_google_drive_by_api(resource_id, token=creds)


def get_file_from_google_by_download_method(
    resource_id: str, method: GoogleDriveFileDownloadMethod
) -> GoogleDriveFileData:
    print(resource_id, method)
    if method == GoogleDriveFileDownloadMethod.API_SERVICE_CREDENTIAL:
        return get_file_from_google_drive_by_api_service_account(resource_id)
    if method == GoogleDriveFileDownloadMethod.API_TOKEN:
        return get_file_from_google_drive_by_api(resource_id)
    if method == GoogleDriveFileDownloadMethod.REQUESTS:
        return GoogleDriveFileData(
            name="submission.ipynb",
            mime_type="",
            content=str(
                get_file_from_google_drive_by_requests(resource_id), encoding="utf_8"
            ),
        )
    raise SystemLogicalError("Unexpected method", method=method)


def get_file_from_google_drive(
    resource_id: str,
    default_method: GoogleDriveFileDownloadMethod,
    /,
    *,
    fallbacks: Sequence[GoogleDriveFileDownloadMethod] = (),
) -> GoogleDriveFileData:
    exc_list: List[Exception] = []
    try:
        return get_file_from_google_by_download_method(resource_id, default_method)
    except GoogleDriveApiException:
        raise
    except Exception as exc:  # pylint: disable=broad-except
        SLACK_NOTIFIER.critical(
            "Colab link submission: Unexpected exception",
            tracebacks=traceback.format_exc(),
        )
        exc_list.append(exc)

    if fallbacks:
        SLACK_NOTIFIER.warning("Colab link submission: fallback is used")
        for fallback_method in fallbacks:
            try:
                return get_file_from_google_by_download_method(
                    resource_id, fallback_method
                )
            except GoogleDriveApiException:
                raise
            except Exception as exc:  # pylint: disable=broad-except
                SLACK_NOTIFIER.critical(
                    "Colab link submission: Unexpected exception",
                    tracebacks=traceback.format_exc(),
                )
                exc_list.append(exc)

    raise SystemResponsibleException(
        "Google Drive API credential is missing", exc_list=exc_list
    )
