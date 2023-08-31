import csv
import dataclasses
import datetime
import io
from typing import Any, Iterable


def convert_dataclasses_to_csv_str(base_data_type: type, data: Iterable[Any]) -> str:
    """
    :param `base_data_type`: `dataclasses.dataclass` を継承しているデータ型 ヘッダー行生成に利用される
    :param `data`: `base_data_type` 型のデータ列を返すイテラブル
    """
    field_names = tuple(field.name for field in dataclasses.fields(base_data_type))
    buffer = io.StringIO()
    csv_writer = csv.DictWriter(buffer, field_names)
    csv_writer.writeheader()
    for row in data:
        csv_writer.writerow(dataclasses.asdict(row))
    return buffer.getvalue()


def iso8601_on_user_timezone(
    date_time: datetime.datetime, user_timezone: datetime.timezone
) -> str:
    return date_time.astimezone(user_timezone).isoformat()
