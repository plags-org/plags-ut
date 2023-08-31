import dataclasses
import os

from judge_core.exercise_concrete.common.schema_util import SettingValidationError
from judge_core.exercise_concrete.schema_loader import (
    SchemaVersion,
    SettingSchemaLatest,
    load_setting,
)


@dataclasses.dataclass
class ExerciseConcrete:
    setting: SettingSchemaLatest
    schema_version: SchemaVersion


def __assert_is_dir(expect_dir: str) -> None:
    if os.path.isdir(expect_dir):
        return
    raise SettingValidationError(f"[ERROR] directory `{expect_dir}` is required")


def load_exercise_concrete(exercise_concrete_dir: str) -> ExerciseConcrete:
    """
    期待される ExerciseConcrete のディレクトリ構成

    ```bash
    $ tree {{ exercise_concrete_dir }}
    {{ exercise_concrete_dir }}/
    ├── {{ STATE_NAME }}.py     # 必要なだけ
    └── setting.json            # 必須

    # あとで考える
    ├── examples                    # 任意
    │   └── {{ EXAMPLE_NAME }}          # 任意
    │       └── {{ submission }}.py         # 任意
    ```
    """
    __assert_is_dir(exercise_concrete_dir)
    # __assert_is_dir(examples_dir := os.path.join(exercise_concrete_dir, 'examples'))

    tests_setting_json_path = os.path.join(exercise_concrete_dir, "setting.json")
    setting, schema_version = load_setting(tests_setting_json_path)
    return ExerciseConcrete(setting=setting, schema_version=schema_version)
