from django.conf import settings

from app_front.config.config import APP_CONFIG
from app_front.core.system_notification.slack import build_configuration
from app_front.core.system_variable import software_name_with_env
from app_front.utils.alert_util import SlackNotifier

# NOTE 悪用厳禁
# print(APP_CONFIG.SYSTEM_NOTIFICATION.SLACK.channel_name)
# print(APP_CONFIG.SYSTEM_NOTIFICATION.SLACK.webhook_url)
SLACK_NOTIFIER = SlackNotifier(
    build_configuration(APP_CONFIG.SYSTEM_NOTIFICATION.SLACK)
)

SLACK_NOTIFIER.info(
    f"{software_name_with_env()} launched on {settings.SERVER_HOSTNAME}."
)

# for DEBUG
# SLACK_NOTIFIER.test_notification()
