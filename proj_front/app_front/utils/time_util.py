import datetime
from typing import Optional

from django.utils import timezone


def get_current_datetime() -> datetime.datetime:
    """
    モックテスト用も兼ねて関数を分離した。これで簡単に手元で未来の時刻下でのテストができる。
    """
    return timezone.now()
    # return timezone.now() - timezone.timedelta(days=46)


def get_earliest_valid_datetime(
    *args: Optional[datetime.datetime], default: Optional[datetime.datetime] = None
) -> datetime.datetime:
    if default:
        return min(filter(None, args), default=default)
    return min(filter(None, args))


def get_latest_valid_datetime(
    *args: Optional[datetime.datetime], default: Optional[datetime.datetime] = None
) -> datetime.datetime:
    if default:
        return max(filter(None, args), default=default)
    return max(filter(None, args))
