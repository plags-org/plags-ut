import dataclasses
import json
from typing import Any, Dict, Final, Optional, Tuple

from typing_extensions import TypeAlias

import judge_core.exercise_concrete.schema_v1_0.loader as v1_0_loader
import judge_core.exercise_concrete.schema_v1_0.schema as v1_0_schema
from judge_core.exercise_concrete.common.schema_util import SettingValidationError


@dataclasses.dataclass
class SchemaLoaderPair:
    schema: Any
    loader: Any


SchemaVersion = str
# NOTE 新しいものを下に追加すること さもないと最新版の計算が壊れる
__SCHEMA_MODULE_TABLE: Final[Dict[SchemaVersion, SchemaLoaderPair]] = {
    v1_0_schema.SCHEMA_VERSION: SchemaLoaderPair(
        schema=v1_0_schema, loader=v1_0_loader
    ),
}
# __LATEST_SCHEMA_VERSION: Final[SchemaVersion] = next(reversed(__SCHEMA_MODULE_TABLE.keys()))
SettingSchemaLatest: TypeAlias = v1_0_schema.Setting


def load_setting(
    setting_filepath: str, schema_version: Optional[str] = None
) -> Tuple[Any, SchemaVersion]:
    with open(setting_filepath, encoding="utf_8") as setting_file:
        setting = json.load(setting_file)

    if schema_version is None:
        schema_version = setting.get("schema_version")
    if schema_version not in __SCHEMA_MODULE_TABLE:
        raise SettingValidationError(f"schema_version {schema_version} does not exist.")

    sl_pair = __SCHEMA_MODULE_TABLE[schema_version]
    valid_setting = sl_pair.loader.load_setting(setting)

    return valid_setting, schema_version
