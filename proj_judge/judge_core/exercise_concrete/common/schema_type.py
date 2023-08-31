"""
スキーマ定義でよく利用される典型的な型の宣言
"""
from typing import Literal, Union

from typing_extensions import TypeAlias


# 64文字以内の文字列
String64: TypeAlias = str

# 64文字以内のASCII文字列
StringAscii64: TypeAlias = str

# 256文字以内のASCII文字列
StringAscii256: TypeAlias = str

# 64文字以内のURLの一部となりうる文字列
# r'[a-zA-Z0-9_-]{1,64}'
StringUrl64: TypeAlias = str

# 1024文字以内の文字列
String1024: TypeAlias = str

# 状態名 ('accept' のみはシステムが予約しているので利用不可)
CustomStateName: TypeAlias = str

# 状態名 (既定の 'accept' を含む)
StateName: TypeAlias = Union[Literal["accept"], CustomStateName]
