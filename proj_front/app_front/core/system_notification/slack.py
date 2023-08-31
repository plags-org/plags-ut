from typing_extensions import TypeAlias

from app_front.utils.alert_util import (
    NotifierConfiguration,
    SlackNotifierGeneralConfiguration,
    SlackNotifierLevelCustomConfiguration,
)
from extension.pydantic_strict import StrictBaseModel

SlackWebhookURL: TypeAlias = str
SlackChannelName: TypeAlias = str


class SlackNotifierConfig(StrictBaseModel):
    """Slack notification configuration via incoming webhook"""

    webhook_url: SlackWebhookURL
    channel_name: SlackChannelName


def build_configuration(config: SlackNotifierConfig) -> NotifierConfiguration:
    return NotifierConfiguration(
        general=SlackNotifierGeneralConfiguration(
            channel=config.channel_name,
            heading="PLAGS Notifier",
            heading_emoji=":coronavirus:",
            bar_color="#7f7f7f",
            webhook_url=config.webhook_url,
        ),
        info=SlackNotifierLevelCustomConfiguration(
            heading="PLAGS INFO",
            heading_emoji=":eyes:",
            bar_color="#00cf00",
        ),
        warning=SlackNotifierLevelCustomConfiguration(
            heading="PLAGS WARNING",
            heading_emoji=":confused:",
            bar_color="#FFFB32",
        ),
        error=SlackNotifierLevelCustomConfiguration(
            heading="*PLAGS ERROR*",
            heading_emoji=":angry:",
            bar_color="#FF0000",
        ),
        critical=SlackNotifierLevelCustomConfiguration(
            heading="*PLAGS CRITICAL*",
            heading_emoji=":imp:",
            bar_color="#8A0B69",
        ),
    )
