"""
Defines application configuration model
"""
from typing import Literal, Sequence, Union

from pydantic import AnyUrl, ConstrainedStr, Field
from typing_extensions import Annotated, TypeAlias

from app_front.core.google_drive.types import GoogleDriveFileDownloadMethod
from app_front.core.system_notification.slack import SlackNotifierConfig
from app_front.core.types import GoogleClientId, MailHostName, RelativeFilePath
from extension.pydantic_strict import StrictBaseModel


class AdministrationPassphrase(ConstrainedStr):
    strict = True
    min_length = 8
    max_length = 64


class AppAdministrationConfig(StrictBaseModel):
    """システム管理の設定"""

    data_migration_passphrase: AdministrationPassphrase
    send_mail_bulk_passphrase: AdministrationPassphrase


class AppGoogleOauthConfig(StrictBaseModel):
    """システムによる Google ユーザー操作の代行: OAuth 同意画面のためのクライアント情報"""

    client_id: GoogleClientId
    client_secrets_file: RelativeFilePath


class AppGoogleAuthConfig(AppGoogleOauthConfig):
    """Google Auth"""

    hosted_domain: MailHostName


class AppGoogleDriveConfig(StrictBaseModel):
    """Google Drive file fetching methods"""

    FILE_DOWNLOAD_METHOD: GoogleDriveFileDownloadMethod
    FILE_DOWNLOAD_METHOD_FALLBACKS: Sequence[GoogleDriveFileDownloadMethod]


class AppSystemMailGoogleGmailApiConfig(AppGoogleOauthConfig):
    """システムによるメールの送信方法: Google Gmail API のためのクライアント情報"""


################################################################
# メールを送信する代わりにシステム通知へメール内容を転送する機能
# cf. _redirect_email_to_system_notification function in app_front/utils/email_util.py


class AppSystemMailRedirectToSystemNotificationEnabled(StrictBaseModel):
    enable: Literal[True]
    method: Literal["SLACK"]


class AppSystemMailRedirectToSystemNotificationDisabled(StrictBaseModel):
    enable: Literal[False]


AnyAppSystemMailRedirectToSystemNotification: TypeAlias = Annotated[
    Union[
        AppSystemMailRedirectToSystemNotificationEnabled,
        AppSystemMailRedirectToSystemNotificationDisabled,
    ],
    Field(discriminator="enable"),
]


class AppSystemMail(StrictBaseModel):
    """システムによるメール送信の挙動を制御する設定"""

    GOOGLE_GMAIL_API: AppSystemMailGoogleGmailApiConfig

    REDIRECT_TO_SYSTEM_NOTIFICATION: AnyAppSystemMailRedirectToSystemNotification


class JudgeApiToken(ConstrainedStr):
    strict = True
    regex = r"^[0-9A-Za-z]+$"
    min_length = 40
    max_length = 64


class AppJudgeConfig(StrictBaseModel):
    """Judge integration"""

    ENDPOINT_URL: AnyUrl
    API_TOKEN: JudgeApiToken


AppSystemNotificationSlack: TypeAlias = SlackNotifierConfig


class AppSystemNotification(StrictBaseModel):
    SLACK: AppSystemNotificationSlack


class AppConfig(StrictBaseModel):
    ADMINISTRATION: AppAdministrationConfig
    GOOGLE_AUTH: AppGoogleAuthConfig
    GOOGLE_DRIVE: AppGoogleDriveConfig
    SYSTEM_MAIL: AppSystemMail
    JUDGE: AppJudgeConfig
    SYSTEM_NOTIFICATION: AppSystemNotification
