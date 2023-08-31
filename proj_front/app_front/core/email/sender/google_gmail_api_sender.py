"""
SMTP サーバーに接続しメールを送信する
"""
import base64
import json

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .interface import (
    BaseMailSender,
    GoogleGmailApiMailSenderConfig,
    MailSenderConfig,
    SendingEmail,
)


class GoogleGmailApiMailSender(BaseMailSender):
    @classmethod
    def send(cls, sending_email: SendingEmail, /, *, config: MailSenderConfig) -> None:
        assert isinstance(config, GoogleGmailApiMailSenderConfig), config.type

        # cf. <https://developers.google.com/gmail/api/guides/sending#sending_messages>

        credentials_json = json.loads(config.credentials_json_str)
        credentials = Credentials.from_authorized_user_info(credentials_json)

        service = build("gmail", "v1", credentials=credentials)

        message = sending_email.build_email_message()

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"raw": encoded_message}

        try:
            # pylint:disable=no-member
            send_message = (
                service.users()
                .messages()
                .send(userId="me", body=create_message)
                .execute()
            )
            print(f'Message Id: {send_message["id"]}')
        except RefreshError as error:
            print(f"An error occurred: {error}")
            send_message = None
            raise
        except HttpError as error:
            print(f"An error occurred: {error}")
            send_message = None
            raise

        # return send_message
