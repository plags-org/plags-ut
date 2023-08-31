"""
メール送信系のインターフェイス実装
"""
import abc
import datetime
import enum
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate
from typing import Literal, Optional, Sequence, Union

from pydantic import EmailStr, Field
from typing_extensions import Annotated, TypeAlias

from app_front.core.types import MailHostName
from extension.pydantic_strict import StrictBaseModel


class SendingEmailAddress(StrictBaseModel):
    email: EmailStr
    display_name: Optional[str] = None

    def __str__(self) -> str:
        if self.display_name is not None:
            return f"{self.display_name} <{self.email}>"
        return self.email


class SenderTypeEnum(str, enum.Enum):
    GOOGLE_GMAIL_API = "GOOGLE_GMAIL_API"
    SMTP = "SMTP"


class _BaseMailSenderConfig(StrictBaseModel):
    type: SenderTypeEnum


class SmtpMailSenderConfig(_BaseMailSenderConfig):
    type: Literal[SenderTypeEnum.SMTP]

    smtp_hostname: MailHostName
    smtp_port: int


class GoogleGmailApiMailSenderConfig(_BaseMailSenderConfig):
    type: Literal[SenderTypeEnum.GOOGLE_GMAIL_API]

    credentials_json_str: str


MailSenderConfig: TypeAlias = Annotated[
    Union[
        SmtpMailSenderConfig,
        GoogleGmailApiMailSenderConfig,
    ],
    Field(discriminator="type"),
]


class SendingEmail(StrictBaseModel):
    from_address: SendingEmailAddress
    to_addresses: Sequence[SendingEmailAddress]

    subject: str

    Content_Plain: str  # pylint: disable=invalid-name
    Content_HTML: Optional[str] = None  # pylint: disable=invalid-name

    def get_To(self) -> str:  # pylint: disable=invalid-name
        return ", ".join(map(str, self.to_addresses))

    def get_From(self) -> str:  # pylint: disable=invalid-name
        return str(self.from_address)

    def build_from_addr(self) -> str:
        return self.get_From()

    def build_to_addrs(self) -> str:
        return self.get_To()

    def get_Subject(self) -> str:  # pylint: disable=invalid-name
        return self.subject

    def build_email_message(self) -> Message:
        message: Message
        if self.Content_HTML is None:
            message = MIMEText(self.Content_Plain)
        else:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(self.Content_Plain, "plain"))
            message.attach(MIMEText(self.Content_HTML, "html"))

        message["To"] = self.get_To()
        message["From"] = self.get_From()
        message["Subject"] = self.get_Subject()
        message["Date"] = formatdate()

        # anti spam-determination (List-Unsubscribe)
        # msg['Reply-To'] = "Google <abc@juge.com>"
        # msg.add_header('List-Unsubscribe', '<http://somelink.com>')

        # anti spam-determination (Message-ID)
        message[
            "Message-ID"
        ] = f"{datetime.datetime.now().timestamp():10.6f}__{self.get_From()}"
        return message


class BaseMailSender:
    @classmethod
    @abc.abstractmethod
    def send(cls, sending_email: SendingEmail, /, *, config: MailSenderConfig) -> None:
        raise NotImplementedError
