"""
何かがやばいときに開発者に知らせるためのもの

Slackに通知したり、メールを送ったりすることを想定している
"""
import dataclasses
import enum
import json
import traceback
from typing import Dict, Optional, final

import requests


class NotifyLevel(enum.Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@final
@dataclasses.dataclass
class SlackNotifierGeneralConfiguration:
    channel: str
    heading: str
    heading_emoji: str
    bar_color: str
    webhook_url: str


@final
@dataclasses.dataclass
class SlackNotifierLevelCustomConfiguration:
    channel: Optional[str] = None
    heading: Optional[str] = None
    heading_emoji: Optional[str] = None
    bar_color: Optional[str] = None
    webhook_url: Optional[str] = None


class NotifierConfiguration:
    def __init__(
        self,
        general: SlackNotifierGeneralConfiguration,
        *,
        info: Optional[SlackNotifierLevelCustomConfiguration] = None,
        warning: Optional[SlackNotifierLevelCustomConfiguration] = None,
        error: Optional[SlackNotifierLevelCustomConfiguration] = None,
        critical: Optional[SlackNotifierLevelCustomConfiguration] = None,
        cache: bool = True,
    ) -> None:
        """
        param: general, info, warning, error, critical: instances of the same Configuration (dataclass) or None
        param: cache: bool, if True, cache configuration for each level
        """
        self.general = general
        self.info = info
        self.warning = warning
        self.error = error
        self.critical = critical
        self.cache: Optional[
            Dict[NotifyLevel, SlackNotifierGeneralConfiguration]
        ] = None
        if cache:
            self._cache_configuration()

    @staticmethod
    def _inherit_configuration(
        general: SlackNotifierGeneralConfiguration,
        target: Optional[SlackNotifierLevelCustomConfiguration],
    ) -> SlackNotifierGeneralConfiguration:
        if target is None:
            target = general
        return type(general)(
            **{
                field.name: getattr(target, field.name) or getattr(general, field.name)
                for field in dataclasses.fields(general)
            }
        )

    def _cache_configuration(self) -> None:
        self.cache = {
            level: self._inherit_configuration(self.general, getattr(self, level.value))
            for level in NotifyLevel
        }

    def get_for_level(
        self, notify_level: NotifyLevel
    ) -> SlackNotifierGeneralConfiguration:
        if self.cache:
            return self.cache[notify_level]
        return self._inherit_configuration(
            self.general, getattr(self, notify_level.value)
        )


class SlackNotifier:
    def __init__(self, configuration: NotifierConfiguration) -> None:
        self.configuration = configuration

    def general(
        self, notify_level: NotifyLevel, message: str, tracebacks: Optional[str] = None
    ) -> None:
        try:
            assert isinstance(notify_level, NotifyLevel), notify_level
            level_configuration = self.configuration.get_for_level(notify_level)
            value = f"""{level_configuration.heading_emoji} {level_configuration.heading}\n{message}"""
            blocks = []
            blocks.append(
                {"type": "section", "text": {"type": "mrkdwn", "text": value}}
            )
            if tracebacks:
                blocks.append({"type": "divider"})
                blocks.append(
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            # 制限をつけないと 400 invalid attachments が出た 具体的な条件は不明
                            "text": tracebacks[:2048]
                            + " ..." * (len(tracebacks) >= 2048),
                        },
                    }
                )

            payload = {
                "channel": level_configuration.channel,
                # "text": message,
                "attachments": [
                    {
                        "blocks": blocks,
                        "color": level_configuration.bar_color,
                    }
                ],
            }
            # print(payload)
            # print(json.dumps(payload, indent=1))
            result = requests.post(
                level_configuration.webhook_url, json.dumps(payload), timeout=4.0
            )
            if result.status_code != 200:
                print(result.status_code, result.url, result.text)

        except Exception:  # pylint: disable=broad-except
            # NOTE エラー通知がエラー落ちするのはまずいから
            traceback.print_exc()

    def info(self, message: str, tracebacks: Optional[str] = None) -> None:
        self.general(NotifyLevel.INFO, message, tracebacks)

    def warning(self, message: str, tracebacks: Optional[str] = None) -> None:
        self.general(NotifyLevel.WARNING, message, tracebacks)

    def error(self, message: str, tracebacks: Optional[str] = None) -> None:
        self.general(NotifyLevel.ERROR, message, tracebacks)

    def critical(self, message: str, tracebacks: Optional[str] = None) -> None:
        self.general(NotifyLevel.CRITICAL, message, tracebacks)

    def test_notification(self) -> None:
        self.info("test-info")
        self.warning("test-warning")
        self.error("test-error")
        self.critical("test-critical")
        try:
            raise AssertionError("Everything is true and false.")
        except AssertionError:
            self.error("test-error", tracebacks=traceback.format_exc())
