import datetime
from typing import Literal, Optional, Union

from pydantic import EmailStr, Field, parse_obj_as
from typing_extensions import Annotated, TypeAlias

from app_front.core.user import get_username_nullable
from app_front.models import SystemSetting
from app_front.utils.exception_util import SystemResourceError
from extension.pydantic_strict import StrictBaseModel


def get_system_settings() -> SystemSetting:
    try:
        system_settings = SystemSetting.objects.get(id=1)
    except SystemSetting.DoesNotExist:
        SystemSetting.objects.create()
        try:
            system_settings = SystemSetting.objects.get(id=1)
        except SystemSetting.DoesNotExist as exc:
            raise SystemResourceError(
                "SystemSetting record does not exist and can not be created"
            ) from exc

    return system_settings


class SystemEmailSenderData(StrictBaseModel):
    email: EmailStr
    name: str
    updated_at: datetime.datetime
    updated_by__username: str
    credentials_json_str: str


def get_system_mail_sender_data() -> Optional[SystemEmailSenderData]:
    system_settings = get_system_settings()
    if system_settings.email_sender_google_credentials_json_str is None:
        return None
    return SystemEmailSenderData(
        email=system_settings.email_sender_google_id_info_email,  # type:ignore[arg-type]
        name=system_settings.email_sender_google_id_info_name,  # type:ignore[arg-type]
        updated_at=system_settings.email_sender_updated_at,  # type:ignore[arg-type]
        updated_by__username=get_username_nullable(
            system_settings.email_sender_updated_by
        ),  # type:ignore[arg-type]
        credentials_json_str=system_settings.email_sender_google_credentials_json_str,
    )


class SystemEmailToAddressOverrideEnabled(StrictBaseModel):
    enabled: Literal[True]
    email: EmailStr


class SystemEmailToAddressOverrideDisabled(StrictBaseModel):
    enabled: Literal[False]
    email: Optional[EmailStr]


AnySystemEmailToAddressOverride: TypeAlias = Annotated[
    Union[
        SystemEmailToAddressOverrideEnabled,
        SystemEmailToAddressOverrideDisabled,
    ],
    Field(discriminator="enabled"),
]


def get_to_address_override_config() -> AnySystemEmailToAddressOverride:
    system_settings = get_system_settings()
    return parse_obj_as(
        AnySystemEmailToAddressOverride,  # type:ignore[arg-type]
        {
            "enabled": system_settings.email_to_address_override_enabled,
            "email": system_settings.email_to_address_override_email,
        },
    )
