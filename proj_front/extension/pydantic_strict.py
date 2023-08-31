"""
`pydantic.BaseModel` の設定をより厳密にしたもの
"""
from typing import Literal

from pydantic import BaseConfig, BaseModel, Extra


class StrictBaseConfig(BaseConfig):
    validate_assignment = True  # default: False
    copy_on_model_validation: Literal["deep"] = "deep"  # default: "shallow"
    validate_all = True  # default: False
    # for DEBUG
    extra: Extra = Extra.forbid  # default: Extra.ignore


class StrictBaseModel(BaseModel):
    class Config(StrictBaseConfig):
        pass
