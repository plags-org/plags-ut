import dataclasses
from typing import Any, Dict, Generic, Hashable, Sequence, Tuple, TypeVar

TDifferenceItem = TypeVar("TDifferenceItem")
TItemKey = Hashable
TItemValue = Any


@dataclasses.dataclass
class FromToPair(Generic[TDifferenceItem]):
    from_item: TDifferenceItem
    to_item: TDifferenceItem


class DifferenceDetector(Generic[TDifferenceItem]):
    def __init__(
        self,
        from_items: Sequence[TDifferenceItem],
        to_items: Sequence[TDifferenceItem],
        *,
        key_attr_name: str,
        value_attr_names: Sequence[str],
    ) -> None:
        self._inserted: Sequence[TDifferenceItem] = []
        self._deleted: Sequence[TDifferenceItem] = []
        self._kept: Sequence[FromToPair] = []
        self._updated: Sequence[FromToPair] = []

        def get_key_mapping(
            items: Sequence[TDifferenceItem],
        ) -> Dict[TItemKey, TDifferenceItem]:
            return {getattr(item, key_attr_name): item for item in items}

        from_key_mapping: Dict[TItemKey, TDifferenceItem] = get_key_mapping(from_items)
        to_key_mapping: Dict[TItemKey, TDifferenceItem] = get_key_mapping(to_items)

        def extract_item_values(item: TDifferenceItem) -> Tuple[TItemValue, ...]:
            return tuple(
                getattr(item, value_attr_name) for value_attr_name in value_attr_names
            )

        def is_updated(pair: FromToPair) -> bool:
            return extract_item_values(pair.from_item) != extract_item_values(
                pair.to_item
            )

        for key in from_key_mapping:
            if key in to_key_mapping:
                pair = FromToPair(
                    from_item=from_key_mapping[key], to_item=to_key_mapping[key]
                )
                if is_updated(pair):
                    self._updated.append(pair)
                else:
                    self._kept.append(pair)
            else:
                self._deleted.append(from_key_mapping[key])
        for key, item in to_key_mapping.items():
            if key not in from_key_mapping:
                self._inserted.append(item)

    @property
    def inserted(self) -> Sequence[TDifferenceItem]:
        return self._inserted

    @property
    def deleted(self) -> Sequence[TDifferenceItem]:
        return self._deleted

    @property
    def kept(self) -> Sequence[FromToPair]:
        return self._kept

    @property
    def updated(self) -> Sequence[FromToPair]:
        return self._updated
