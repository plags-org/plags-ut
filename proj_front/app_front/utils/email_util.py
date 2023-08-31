"""システムから送信するEメールの実装
"""
import dataclasses
import datetime
import enum
import re
import traceback
from typing import Optional, Tuple

import pytz
from django.conf import settings
from django.urls import reverse

from app_front.config.config import APP_CONFIG
from app_front.config.config_model import (
    AppSystemMailRedirectToSystemNotificationEnabled,
)
from app_front.core.email.sender.interface import (
    GoogleGmailApiMailSenderConfig,
    MailSenderConfig,
    SenderTypeEnum,
    SendingEmail,
    SendingEmailAddress,
)
from app_front.core.email.sender.sender import send_email
from app_front.core.system_settings import (
    SystemEmailToAddressOverrideEnabled,
    get_system_mail_sender_data,
    get_to_address_override_config,
)
from app_front.core.system_variable import software_name_with_env
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import EmailHistory, TransitoryUser, User
from app_front.utils.exception_util import SystemLogicalError

_DEFAULT_EMAIL_SUBJECT = "[PLAGS UT] {objective}"

# NOTE How to test spamminess
# send mail to 'test-r6fi46o2f@srv1.mail-tester.com'
# and check <https://www.mail-tester.com/test-r6fi46o2f>
# Score 6.2 -> 7.1 -> 7.9
# -1 is from DKIM, -1 is from broken URL, so almost perfect!!

_DEFAULT_REGISTERED_AS_SYSTEM_EMAIL_SENDER_ACCOUNT_NOTIFICATION_EMAIL_BODY__TEXT_HTML = """\
<html>\
<head></head>\
<body>\
<h3>Dear {email},</h3>

<p>Welcome to PLAGS UT, Programming Lecture Auto Grading System for UTokyo.</p>

<p>Your Google account (this email) is registered as a system email sender for PLAGS UT.</p>

<p>To modify this configuration, access to <a href="{system_email_setting_url}">{system_email_setting_url}</a> page.</p>

---

<p>You are receiving this e-mail because password reset is requested for your PLAGS UT account.</p>
<p>If you do not understand the content of this email, please discard this email.</p>
<p>This email is delivered from the email address for sending only. Please note that we will not be able to reply even if you reply as is.</p>
</body>\
</html>\
"""

DEFAULT_ACTIVATION_EMAIL_BODY__TEXT_HTML = """\
<html>\
<head></head>\
<body>\
<h3>Dear {email},</h3>

<p>Welcome to PLAGS UT, Programming Lecture Auto Grading System for UTokyo.

<p>With the following information, you can complete your PLAGS UT account activation.</p>

<ul>\
<li><p>Your mail address: {email}</p></li>
<li><p>Your "Activation PIN": {activation_pin}</p></li>
</ul>\

<p>Activation PIN expires at <code>{expires_at_str}</code>{expiration_period}.</p>

<p>Activate your account from <a href="{register_activate_url}">{register_activate_url}</a> .</p>

---

<p>If you do not understand the content of this email, please discard this email.</p>
<p>This email is delivered from the email address for sending only. Please note that we will not be able to reply even if you reply as is.</p>
</body>\
</html>\
"""

DEFAULT_RESET_PASSWORD_EMAIL_BODY__TEXT_HTML = """\
<html>\
<head></head>\
<body>\
<h3>Dear {email},</h3>

<p>Welcome to PLAGS UT, Programming Lecture Auto Grading System for UTokyo.

<p>With the following information, you can reset your password and recover your account.</p>

<ul>\
<li><p>Your mail address: {email}</p></li>
<li><p>Your "Password reset PIN": {password_reset_pin}</p></li>
</ul>\

<p>Recover your account from <a href="{password_reset_confirm_url}">{password_reset_confirm_url}</a> .</p>

---

<p>You are receiving this e-mail because password reset is requested for your PLAGS UT account.</p>
<p>If you do not understand the content of this email, please discard this email.</p>
<p>This email is delivered from the email address for sending only. Please note that we will not be able to reply even if you reply as is.</p>
</body>\
</html>\
"""

DEFAULT_EMAIL_UPDATE_EMAIL_BODY__TEXT_HTML = """\
<html>\
<head></head>\
<body>\
<h3>Dear {email},</h3>

<p>Welcome to PLAGS UT, Programming Lecture Auto Grading System for UTokyo.</p>

<p>With the following information, you can update account ID for your account.</p>

<ul>\
<li><p>Your new account ID: {email}</p></li>
<li><p>Your "Account update PIN": {email_update_pin}</p></li>
</ul>\

<p>Apply this account ID by filling "Step 2" form from <a href="{email_update_url}">{email_update_url}</a> .</p>

---

<p>You are receiving this e-mail because this address has registered to PLAGS UT for updating email address for existing account.</p>
<p>If you do not understand the content of this email, please discard this email.</p>
<p>This email is delivered from the email address for sending only. Please note that we will not be able to reply even if you reply as is.</p>
</body>\
</html>\
"""

DEFAULT_CONFIRM_COMMON_ID_NUMBER_EMAIL_BODY__TEXT_HTML = """\
<html>\
<head></head>\
<body>\
<h3>Dear {email},</h3>

<p>Welcome to PLAGS UT, Programming Lecture Auto Grading System for UTokyo.</p>

<p>With the following information, your common ID number will be linked to your PLAGS UT account.</p>

<ul>\
<li><p>Your account ID: {email} (Google login address: {google_id_info_email})</p></li>
<li><p>Your common ID number: {common_id_number}</p></li>
<li><p>"Verification token": {cin_verification_token}</p></li>
</ul>\

<p>Verify your common ID number from <a href="{profile_url}">{profile_url}</a> with "Verification token" above.</p>

---

<p>You are receiving this e-mail because your common ID number has registered to PLAGS UT for account verification.</p>
<p>If you do not understand the content of this email, please discard this email.</p>
<p>This email is delivered from the email address for sending only. Please note that we will not be able to reply even if you reply as is.</p>
</body>\
</html>\
"""



@dataclasses.dataclass
class PlagsEmailData:
    sending_email: SendingEmail

    sender_config: MailSenderConfig

    to_user: Optional[User]
    to_transitory_user: Optional[TransitoryUser]
    objective: str

    @classmethod
    def make_sender_config_and_from_address(
        cls,
    ) -> Tuple[MailSenderConfig, SendingEmailAddress]:
        # MAYBE implement fallback (?)
        # return SmtpMailSenderConfig()
        system_mail_sender_data = get_system_mail_sender_data()
        assert system_mail_sender_data is not None

        return (
            GoogleGmailApiMailSenderConfig(
                type=SenderTypeEnum.GOOGLE_GMAIL_API,
                credentials_json_str=system_mail_sender_data.credentials_json_str,
            ),
            SendingEmailAddress(
                email=system_mail_sender_data.email,
                display_name=software_name_with_env(),
            ),
        )

    @classmethod
    def make_with_sender_config(
        cls,
        from_address: SendingEmailAddress,
        to_address: Optional[str],
        objective: str,
        subject: str,
        Content_Plain: str,  # pylint: disable=invalid-name
        Content_HTML: str,  # pylint: disable=invalid-name
        sender_config: MailSenderConfig,
        to_user: Optional[User],
        to_transitory_user: Optional[TransitoryUser],
    ) -> "PlagsEmailData":
        return PlagsEmailData(
            sending_email=SendingEmail(
                from_address=from_address,
                to_addresses=[SendingEmailAddress(email=to_address)],
                subject=subject.format(objective=objective),
                Content_Plain=Content_Plain,
                Content_HTML=Content_HTML,
            ),
            sender_config=sender_config,
            to_user=to_user,
            to_transitory_user=to_transitory_user,
            objective=objective,
        )

    @classmethod
    def make(
        cls,
        to_address: Optional[str],
        objective: str,
        subject: str,
        Content_Plain: str,  # pylint: disable=invalid-name
        Content_HTML: str,  # pylint: disable=invalid-name
        to_user: Optional[User],
        to_transitory_user: Optional[TransitoryUser],
    ) -> "PlagsEmailData":
        sender_config, from_address = cls.make_sender_config_and_from_address()
        return cls.make_with_sender_config(
            from_address=from_address,
            to_address=to_address,
            objective=objective,
            subject=subject,
            Content_Plain=Content_Plain,
            Content_HTML=Content_HTML,
            sender_config=sender_config,
            to_user=to_user,
            to_transitory_user=to_transitory_user,
        )


class RenderEmailMode(enum.Enum):
    TEXT_PLAIN = "text/plain"
    TEXT_HTML = "text/html"


def clean_html_tags(content_html: str) -> str:
    return re.sub(r"\<.*?\>", "", content_html)


def get_plain_from_html(content_html: str) -> str:
    email_body_replaced_li = content_html.replace("<li>", "<li>* ")
    return clean_html_tags(email_body_replaced_li)


def render_email_body(
    email_body_template: str, params: dict, /, *, mode: RenderEmailMode
) -> str:
    if mode == RenderEmailMode.TEXT_PLAIN:
        content_plain = get_plain_from_html(email_body_template)
        return content_plain.format(**params)

    if mode == RenderEmailMode.TEXT_HTML:
        return email_body_template.format(**params)

    raise ValueError(f"Invalid mode: {mode}")


@dataclasses.dataclass
class PlagsEmailSendResult:
    success: bool
    email_history: Optional[EmailHistory]


def _override_email_to_address(
    email: PlagsEmailData, /, *, config: SystemEmailToAddressOverrideEnabled
) -> PlagsEmailData:
    new_subject = (
        "To [ " + email.sending_email.get_To() + " ] " + email.sending_email.subject
    )
    new_to_addresses = (SendingEmailAddress(email=config.email),)

    return PlagsEmailData(
        sending_email=SendingEmail(
            from_address=email.sending_email.from_address,
            to_addresses=new_to_addresses,
            subject=new_subject,
            Content_Plain=email.sending_email.Content_Plain,
            Content_HTML=email.sending_email.Content_HTML,
        ),
        sender_config=email.sender_config,
        to_user=email.to_user,
        to_transitory_user=email.to_transitory_user,
        objective=email.objective,
    )


def _redirect_email_to_system_notification(
    email: PlagsEmailData,
    email_history: EmailHistory,
    /,
    *,
    config: AppSystemMailRedirectToSystemNotificationEnabled,
) -> PlagsEmailSendResult:
    """メールを送信する代わりにシステム通知へメール内容を転送する

    - HINT 主に local 環境で用いることが想定される"""
    if config.method == "SLACK":
        SLACK_NOTIFIER.info(
            f"To      : {email.sending_email.get_To()}\n"
            f"From    : {email.sending_email.get_From()}\n"
            f"Subject : {email.sending_email.get_Subject()}\n"
            f"Body    :\n{email.sending_email.Content_Plain}"
        )
        return PlagsEmailSendResult(success=True, email_history=email_history)
    raise NotImplementedError(config.method)


def _create_email_history(email: PlagsEmailData) -> EmailHistory:
    """メール送信履歴を記録する"""
    return EmailHistory.objects.create(
        to_user=email.to_user,
        to_transitory_user=email.to_transitory_user,
        objective=email.objective,
        from_address=email.sending_email.build_from_addr(),
        to_address=email.sending_email.build_to_addrs(),
        subject=email.sending_email.get_Subject(),
        content_plain=email.sending_email.Content_Plain,
        content_html=email.sending_email.Content_HTML,
    )


def _send_plags_email(email: PlagsEmailData) -> PlagsEmailSendResult:
    """システムとしてメールを送信する

    - 各種修飾が行われる:
      - `_override_email_to_address`
      - `_redirect_email_to_system_notification`
    """
    to_address_override_config = get_to_address_override_config()
    if to_address_override_config.enabled:
        email = _override_email_to_address(email, config=to_address_override_config)

    # メール送信の記録を残す
    email_history = _create_email_history(email)

    if APP_CONFIG.SYSTEM_MAIL.REDIRECT_TO_SYSTEM_NOTIFICATION.enable:
        return _redirect_email_to_system_notification(
            email,
            email_history,
            config=APP_CONFIG.SYSTEM_MAIL.REDIRECT_TO_SYSTEM_NOTIFICATION,
        )

    return _send_plags_email_impl(email, email_history)


def _send_plags_email_impl(
    email: PlagsEmailData, email_history: EmailHistory
) -> PlagsEmailSendResult:
    """システムとしてメールを送信する（内部実装）

    - ATTENTION 各種修飾は行われないので通常こちらを使うことはない。使用が適切かよく考えること。"""
    smtp_traceback: Optional[str] = None
    try:
        send_email(email.sending_email, config=email.sender_config)
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        smtp_traceback = traceback.format_exc()[:65535]
        message = (
            f"On: {__file__}\n"
            f"Params: {email.objective=} / {email.sending_email.to_addresses=}\n"
            f"Issue: Detected Exception"
        )
        SLACK_NOTIFIER.error(message, tracebacks=traceback.format_exc())
        # raise
    finally:
        if not (success := smtp_traceback is None):
            email_history.smtp_traceback = smtp_traceback
            email_history.save()
            email_history.refresh_from_db()

    return PlagsEmailSendResult(
        success=success,
        email_history=email_history,
    )


def send_registered_as_system_email_sender_account_notification(
    sender_email: str,
    /,
    *,
    credentials_json_str: str,
    protocol_domain: str,
) -> PlagsEmailSendResult:
    """システムメールの送信アカウントとして登録されたことを通知するメールを送信"""

    objective = "You are registered as PLAGS UT system mail sender!"
    subject = _DEFAULT_EMAIL_SUBJECT

    system_email_setting_url = protocol_domain + reverse(
        "administration/system_email_setting"
    )

    params = dict(
        email=sender_email,
        system_email_setting_url=system_email_setting_url,
    )

    email_body_template = _DEFAULT_REGISTERED_AS_SYSTEM_EMAIL_SENDER_ACCOUNT_NOTIFICATION_EMAIL_BODY__TEXT_HTML
    content_plain = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_PLAIN
    )
    content_html = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_HTML
    )

    sender_config = GoogleGmailApiMailSenderConfig(
        type=SenderTypeEnum.GOOGLE_GMAIL_API,
        credentials_json_str=credentials_json_str,
    )
    from_address = SendingEmailAddress(
        email=sender_email, display_name=software_name_with_env()
    )

    email = PlagsEmailData.make_with_sender_config(
        from_address=from_address,
        to_address=sender_email,
        objective=objective,
        subject=subject,
        Content_Plain=content_plain,
        Content_HTML=content_html,
        sender_config=sender_config,
        to_user=None,
        to_transitory_user=None,
    )

    # NOTE _send_plags_email を使うと各種のメール送信への修飾がかかるが、
    #      ここではメールアカウントに確実にメールを送りたいためそのように実装する。
    # return _send_plags_email(email)

    email_history = _create_email_history(email)
    return _send_plags_email_impl(email, email_history)


def send_activation_email(
    to_transitory_user: TransitoryUser,
    protocol_domain: str,
    /,
    *,
    expires_at: datetime.datetime,
    expiration_period: str = "",
) -> PlagsEmailSendResult:
    "有効化方法の通知メールを送信"

    objective = "Activate your account"
    subject = _DEFAULT_EMAIL_SUBJECT

    register_activate_url = protocol_domain + reverse("register/activate")

    expires_at_str = expires_at.astimezone(pytz.timezone(settings.TIME_ZONE)).strftime(
        "%Y-%m-%d %H:%M:%S +%Z"
    )

    params = dict(
        email=to_transitory_user.email,
        activation_pin=to_transitory_user.activation_pin,
        register_activate_url=register_activate_url,
        expires_at_str=expires_at_str,
        expiration_period=expiration_period,
    )

    email_body_template = DEFAULT_ACTIVATION_EMAIL_BODY__TEXT_HTML
    content_plain = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_PLAIN
    )
    content_html = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_HTML
    )

    email = PlagsEmailData.make(
        to_address=to_transitory_user.email,
        objective=objective,
        subject=subject,
        Content_Plain=content_plain,
        Content_HTML=content_html,
        to_user=None,
        to_transitory_user=to_transitory_user,
    )
    return _send_plags_email(email)


def send_email_update_email(
    to_user: User, protocol_domain: str, /, *, resend: bool = False
) -> PlagsEmailSendResult:
    """E-mail更新通知メールを送信"""

    objective = "Updating your email address"
    subject = _DEFAULT_EMAIL_SUBJECT
    if resend:
        subject = "[Re-sending] " + subject

    email_update_url = protocol_domain + reverse("update_email")

    params = dict(
        email=to_user.email_updating_to,
        email_update_pin=to_user.email_update_pin,
        email_update_url=email_update_url,
    )

    email_body_template = DEFAULT_EMAIL_UPDATE_EMAIL_BODY__TEXT_HTML
    content_plain = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_PLAIN
    )
    content_html = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_HTML
    )

    email = PlagsEmailData.make(
        to_address=to_user.email,
        objective=objective,
        subject=subject,
        Content_Plain=content_plain,
        Content_HTML=content_html,
        to_user=to_user,
        to_transitory_user=None,
    )
    return _send_plags_email(email)


def send_password_reset_email(
    to_user: User, protocol_domain: str
) -> PlagsEmailSendResult:
    """パスワード更新通知メールを送信"""

    objective = "Reset your password"
    subject = _DEFAULT_EMAIL_SUBJECT

    password_reset_confirm_url = protocol_domain + reverse(
        "user/reset_password/confirm"
    )

    params = dict(
        email=to_user.email,
        password_reset_pin=to_user.password_reset_pin,
        password_reset_confirm_url=password_reset_confirm_url,
    )

    email_body_template = DEFAULT_RESET_PASSWORD_EMAIL_BODY__TEXT_HTML
    content_plain = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_PLAIN
    )
    content_html = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_HTML
    )

    email = PlagsEmailData.make(
        to_address=to_user.email,
        objective=objective,
        subject=subject,
        Content_Plain=content_plain,
        Content_HTML=content_html,
        to_user=to_user,
        to_transitory_user=None,
    )
    return _send_plags_email(email)


def send_common_id_number_verification_email(
    to_user: User, protocol_domain: str
) -> PlagsEmailSendResult:
    """共通IDの確認メールを送信"""

    objective = "Verify your common ID number"
    subject = _DEFAULT_EMAIL_SUBJECT

    profile_url = protocol_domain + reverse("profile")

    # ATTENTION  to_user.email は使えない（None）
    #     NOTE そもそもこの email を検証するためのメールである
    maybe_common_id_number = to_user.google_id_common_id_number_unverified
    if maybe_common_id_number is None:
        raise SystemLogicalError(
            "to_user.google_id_common_id_number_unverified must be set"
        )
    to_user_email = to_user.build_email_from_common_id_number(maybe_common_id_number)

    params = dict(
        email=to_user_email,
        google_id_info_email=to_user.google_id_info_email,
        common_id_number=to_user.google_id_common_id_number_unverified,
        cin_verification_token=to_user.google_id_common_id_number_verification_token,
        profile_url=profile_url,
    )

    email_body_template = DEFAULT_CONFIRM_COMMON_ID_NUMBER_EMAIL_BODY__TEXT_HTML
    content_plain = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_PLAIN
    )
    content_html = render_email_body(
        email_body_template, params, mode=RenderEmailMode.TEXT_HTML
    )

    email = PlagsEmailData.make(
        to_address=to_user_email,
        objective=objective,
        subject=subject,
        Content_Plain=content_plain,
        Content_HTML=content_html,
        to_user=to_user,
        to_transitory_user=None,
    )
    return _send_plags_email(email)


def send_email_to_user(
    objective: str,
    subject: str,
    body_template: str,
    to_user: User,
    /,
    *,
    body_template_params: dict = None,
    resend: bool = False,
) -> PlagsEmailSendResult:
    if resend:
        subject = "[Re-sending] " + subject

    if body_template_params is None:
        body_template_params = {}

    content_plain = render_email_body(
        body_template, body_template_params, mode=RenderEmailMode.TEXT_PLAIN
    )
    content_html = render_email_body(
        body_template, body_template_params, mode=RenderEmailMode.TEXT_HTML
    )

    email = PlagsEmailData.make(
        to_address=to_user.email,
        objective=objective,
        subject=subject,
        Content_Plain=content_plain,
        Content_HTML=content_html,
        to_user=to_user,
        to_transitory_user=None,
    )
    return _send_plags_email(email)


def send_email_to_address(
    objective: str,
    subject: str,
    body_template: str,
    to_address: str,
    /,
    *,
    body_template_params: dict = None,
    resend: bool = False,
) -> PlagsEmailSendResult:
    if resend:
        subject = "[Re-sending] " + subject

    if body_template_params is None:
        body_template_params = {}

    content_plain = render_email_body(
        body_template, body_template_params, mode=RenderEmailMode.TEXT_PLAIN
    )
    content_html = render_email_body(
        body_template, body_template_params, mode=RenderEmailMode.TEXT_HTML
    )

    email = PlagsEmailData.make(
        to_address=to_address,
        objective=objective,
        subject=subject,
        Content_Plain=content_plain,
        Content_HTML=content_html,
        to_user=None,
        to_transitory_user=None,
    )
    return _send_plags_email(email)
