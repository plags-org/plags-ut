"""
SMTP サーバーに接続しメールを送信する
"""
import smtplib

from .interface import (
    BaseMailSender,
    MailSenderConfig,
    SendingEmail,
    SmtpMailSenderConfig,
)


class SmtpMailSender(BaseMailSender):
    @classmethod
    def send(cls, sending_email: SendingEmail, /, *, config: MailSenderConfig) -> None:
        assert isinstance(config, SmtpMailSenderConfig), config.type

        smtp_client = smtplib.SMTP(config.smtp_hostname, config.smtp_port, timeout=16)
        # smtp_client.set_debuglevel(1)
        smtp_client.ehlo()
        smtp_client.starttls()
        send_errors = smtp_client.sendmail(
            sending_email.from_address.email,
            [address.email for address in sending_email.to_addresses],
            sending_email.build_email_message().as_string(),
        )
        print(f"{send_errors=}")
        smtp_client.quit()

