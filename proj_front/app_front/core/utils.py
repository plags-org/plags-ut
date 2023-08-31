from typing import AbstractSet, Callable, Generic, Hashable, Iterable, Tuple, TypeVar

from typing_extensions import ParamSpec


def block_split_range(total_size: int, block_size: int) -> Iterable[Tuple[int, int]]:
    for block_start in range(0, total_size, block_size):
        block_end = min(block_start + block_size, total_size)
        yield block_start, block_end


_PLazyCall = ParamSpec("_PLazyCall")
_TLazyCallResult = TypeVar("_TLazyCallResult")


class LazyCall(
    Generic[_PLazyCall, _TLazyCallResult]
):  # pylint: disable=too-few-public-methods
    def __init__(
        self,
        func: Callable[_PLazyCall, _TLazyCallResult],
        *args: _PLazyCall.args,
        **kwargs: _PLazyCall.kwargs,
    ) -> None:
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def __call__(self) -> _TLazyCallResult:
        return self.func(*self.args, **self.kwargs)


_TCompareSetValue = TypeVar("_TCompareSetValue", bound=Hashable)


def compare_set(
    set_a: AbstractSet[_TCompareSetValue], set_b: AbstractSet[_TCompareSetValue]
) -> Tuple[AbstractSet[_TCompareSetValue], AbstractSet[_TCompareSetValue]]:
    return (set_a - set_b, set_b - set_a)
