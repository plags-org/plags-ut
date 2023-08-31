from .google_gmail_api_sender import GoogleGmailApiMailSender
from .interface import (
    GoogleGmailApiMailSenderConfig,
    MailSenderConfig,
    SendingEmail,
    SmtpMailSenderConfig,
)
from .smtp_sender import SmtpMailSender


def send_email(sending_email: SendingEmail, /, *, config: MailSenderConfig) -> None:
    """Eメールを送信する

    - 送信方法は `config` の型によって規定される"""
    if isinstance(config, GoogleGmailApiMailSenderConfig):
        return GoogleGmailApiMailSender().send(sending_email, config=config)
    if isinstance(config, SmtpMailSenderConfig):
        return SmtpMailSender().send(sending_email, config=config)
    raise NotImplementedError(sending_email.config)
