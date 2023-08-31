import datetime
import io
from types import TracebackType
from typing import Any, Final, Optional, Type


class Tee:

    def __init__(self, indent: int = 4) -> None:
        self.buf = io.StringIO()
        self.indent = indent
        self.indent_level = 0

    def __base(self, level: str, *objects: Any) -> None:
        indent = " " * (self.indent * self.indent_level)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %Z")
        print(f"{indent}{timestamp}[{level}]", *objects, file=self.buf)
        print(f"{indent}{timestamp}[{level}]", *objects)

    def info(self, *objects: Any) -> None:
        self.__base("INFO", *objects)

    def warning(self, *objects: Any) -> None:
        self.__base("WARNING", *objects)

    def error(self, *objects: Any) -> None:
        self.__base("ERROR", *objects)

    def critical(self, *objects: Any) -> None:
        self.__base("CRITICAL", *objects)

    def phase(self, message: str) -> None:
        self.info("=" * 64)
        self.info("Phase:", message)

    def full_str(self) -> str:
        return self.buf.getvalue()


# 関数引数のデフォルト値などとして使う用
TEE_DEV_NULL: Final = Tee()


class TeeSubPhase:
    def __init__(self, tee: Tee, message: Optional[str] = None):
        self.tee = tee
        self.message = message

    def __enter__(self) -> "TeeSubPhase":
        self.tee.indent_level += 1
        if self.message:
            self.tee.phase(self.message)
        return self

    def __exit__(
        self,
        exception_type: Type[BaseException],
        exception_value: BaseException,
        traceback: TracebackType,
    ) -> None:
        self.tee.indent_level = max(0, self.tee.indent_level - 1)
