"""
evaluator <-> runner 間のインターフェイス定義（runner側が利用するもの）

ATTENTION Runner 側であるため以下の制約がある:

* Python >= 3.10 で動作する必要がある
  * `dataclasses` は利用可能
* 標準モジュールのみで実現する必要がある
  * `pydantic` は利用できない
"""
import dataclasses
from typing import ClassVar, FrozenSet, List, Sequence, Type, TypeVar

# ATTENTION 評価環境内では、非標準モジュールは利用できない可能性がある
try:
    from colorama import Back, Fore, Style
except ImportError:

    class EmptyStringNamespace:
        def __getattribute__(self, name: str) -> str:
            return ""

    Fore = EmptyStringNamespace()  # type:ignore[assignment]
    Back = EmptyStringNamespace()  # type:ignore[assignment]
    Style = EmptyStringNamespace()  # type:ignore[assignment]


_TValue = TypeVar("_TValue")


def _dict_get_as_type(obj: dict, key: str, expect_type: Type[_TValue]) -> _TValue:
    value = obj[key]
    if not isinstance(value, expect_type):
        raise TypeError(value, expect_type)
    return value


# TypeAlias
EvaluationTagName = str


@dataclasses.dataclass
class EvaluationTagData:
    name: EvaluationTagName
    description: str
    background_color: str
    font_color: str
    visible: bool

    def __post_init__(self) -> None:
        # NOTE Pydanticが使えないかわりにvalidatorを自作する
        if not self.name:
            raise ValueError("user name is empty string")

    @classmethod
    def parse_obj(cls, obj: dict) -> "EvaluationTagData":
        if not isinstance(obj, dict):
            raise ValueError(obj)
        data = EvaluationTagData(
            name=_dict_get_as_type(obj, "name", str),
            description=_dict_get_as_type(obj, "description", str),
            background_color=_dict_get_as_type(obj, "background_color", str),
            font_color=_dict_get_as_type(obj, "font_color", str),
            visible=_dict_get_as_type(obj, "visible", bool),
        )
        return data

    def dict(self) -> dict:
        return dataclasses.asdict(self)

    def to_console_view(self) -> str:
        return f"[{self.name}]{{{self.description}}}"


@dataclasses.dataclass
class TestCaseResultData:
    name: str
    # Literal["pass", "fail", "error", "fatal"]
    status: str
    tags: List[EvaluationTagData]
    msg: str  # message欄に出力すべき文字列
    err: str  # unittest.main が生成するstack backtrace
    system_message: str = dataclasses.field(default="")

    def __post_init__(self) -> None:
        # NOTE Pydanticが使えないかわりにvalidatorを自作する
        pass

    @classmethod
    def parse_obj(cls, obj: dict) -> "TestCaseResultData":
        if not isinstance(obj, dict):
            raise ValueError(obj)
        data = TestCaseResultData(
            name=_dict_get_as_type(obj, "name", str),
            status=_dict_get_as_type(obj, "status", str),
            tags=_dict_get_as_type(obj, "tags", list),
            err=_dict_get_as_type(obj, "err", str),
            msg=_dict_get_as_type(obj, "msg", str),
        )
        if data.status not in ("pass", "fail", "error", "unknown"):
            raise ValueError(f"Invalid status: {data.status!r}")
        data.tags = [EvaluationTagData.parse_obj(tag) for tag in data.tags]
        return data

    def dict(self) -> dict:
        return dataclasses.asdict(self)


# TypeAlias
TestStageResult = List[TestCaseResultData]


class ResultTypeCode:
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    FATAL = "fatal"
    UNKNOWN = "unknown"  # 互換性のため


class BuiltinEvaluationTag:
    # worker責任のエラー
    BSE: ClassVar[EvaluationTagData] = EvaluationTagData(
        name="BSE",
        description="Backend System Error",
        background_color="#bb00bb",
        font_color="#ffdfff",
        visible=True,
    )
    ESE: ClassVar[EvaluationTagData] = EvaluationTagData(
        name="ESE",
        description="Evaluation System Error",
        background_color="#dd00dd",
        font_color="#ffdfff",
        visible=True,
    )
    # 実行中の挙動について
    TLE: ClassVar[EvaluationTagData] = EvaluationTagData(
        name="TLE",
        description="Time Limit Exceeded",
        background_color="#ffdf3f",
        font_color="#ffefcf",
        visible=True,
    )
    PV: ClassVar[EvaluationTagData] = EvaluationTagData(
        name="PV",
        description="Permission Violation",
        background_color="#ffdf3f",
        font_color="#ffefcf",
        visible=True,
    )
    UA: ClassVar[EvaluationTagData] = EvaluationTagData(
        name="UA",
        description="Unexpected Abortion",
        background_color="#ff00ff",
        font_color="#ffdfff",
        visible=True,
    )


_BUILTIN_TAG_NAME_SET: FrozenSet[EvaluationTagName] = frozenset(
    key for key in BuiltinEvaluationTag.__dict__ if not key.startswith("__")
)
# print(_BUILTIN_TAG_NAME_SET)

SYSTEM_FAILURE_TAG_NAME_SET: FrozenSet[EvaluationTagName] = frozenset(
    tag.name for tag in (BuiltinEvaluationTag.BSE,)
)


def get_colored_evaluation_tags(tags: Sequence[EvaluationTagData]) -> str:
    statuses_str_list = []
    for tag in tags:
        name = tag.name
        tag_str = tag.to_console_view()
        if name in _BUILTIN_TAG_NAME_SET:
            statuses_str_list.append(
                Fore.LIGHTMAGENTA_EX
                + Back.WHITE
                + Style.BRIGHT
                + f"[!!! JUDGE FAILURE ({tag_str}) !!!]"
            )
        else:
            statuses_str_list.append(Fore.BLUE + Style.BRIGHT + tag_str)
    tags_str = "".join(statuses_str_list)
    if tags_str:
        tags_str += Style.RESET_ALL
    return tags_str
