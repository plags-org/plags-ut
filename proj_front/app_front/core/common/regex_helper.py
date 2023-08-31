"""
正規表現関連の便利実装
"""
import re
from typing import Pattern


def to_fullmatch_regex(regex: str) -> str:
    """`re.match` に入力しても `re.fullmatch` と意味が一致するような正規表現に書き換える"""
    return "^" + regex + "$"


def to_compiled_fullmatch_regex(regex: str) -> Pattern[str]:
    """`re.compile` 済みの `to_fullmatch_regex` を返す"""
    return re.compile(to_fullmatch_regex(regex))
