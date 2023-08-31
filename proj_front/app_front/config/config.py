import os
from typing import Final

from django.conf import settings

from app_front.core.const import UTOKYO_ECCS_MAIL_DOMAIN

from .config_model import AppConfig

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONFIG_DIR = os.path.join(BASE_DIR, "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.ini")

APP_CONFIG: Final[AppConfig] = AppConfig.parse_obj(settings.APP_SETTING)


# NOTE 本番環境での誤設定を阻止するためのassertion
if not settings.IS_LOCAL and not settings.STAGING:
    if APP_CONFIG.GOOGLE_AUTH.hosted_domain != UTOKYO_ECCS_MAIL_DOMAIN:
        raise ValueError(
            f"{APP_CONFIG.GOOGLE_AUTH.hosted_domain=} != {UTOKYO_ECCS_MAIL_DOMAIN=}"
        )
