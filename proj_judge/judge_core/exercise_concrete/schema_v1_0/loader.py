"""
PLAGS UT の自動評価設定のスキーマ定義のローダー
"""
from typing import Any

from pydantic.error_wrappers import ValidationError

from judge_core.exercise_concrete.common.schema_util import SettingValidationError

from .schema import SCHEMA_VERSION, Setting

ERROR_PREFIX = f"Schema({SCHEMA_VERSION}):"


def load_setting(setting: Any) -> Setting:
    try:
        return Setting.parse_obj(setting)
    except ValidationError as exc:
        raise SettingValidationError(exc.json()) from exc
