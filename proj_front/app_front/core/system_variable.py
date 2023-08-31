import functools
from typing import List

from django.conf import settings


@functools.lru_cache(1)
def software_name_with_env() -> str:
    """環境名で修飾されたソフトウェア名を返却する

    - `DEBUG` フラグや `STAGING` フラグが有効な場合は、それとわかるよう prefixing を行う"""
    non_production_envs: List[str] = []
    if settings.DEBUG:
        non_production_envs.append("DEBUG")
    if settings.STAGING:
        non_production_envs.append("STAGING")

    software_name = settings.SOFTWARE_NAME
    if non_production_envs:
        software_name = f'[env:{"+".join(non_production_envs)}] ' + software_name

    return software_name
