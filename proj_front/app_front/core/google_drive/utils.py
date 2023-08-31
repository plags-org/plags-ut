import re

from .const import MAX_FILE_SIZE_DEFAULT


def get_resource_id_from_url(url: str):
    if match := re.search(r"1[-_0-9A-Za-z]{32}", url):
        return match[0]
    return None


def get_max_file_size() -> int:
    return MAX_FILE_SIZE_DEFAULT
