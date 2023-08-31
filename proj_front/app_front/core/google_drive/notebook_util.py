import requests

from .utils import get_max_file_size, get_resource_id_from_url


# NOTE taken from <https://stackoverflow.com/questions/38511444/python-download-files-from-google-drive-using-url>
def get_file_from_google_drive_by_requests(resource_id: str) -> bytes:
    google_drive_download_url = "https://docs.google.com/uc?export=download"

    session = requests.Session()

    response = session.get(
        google_drive_download_url, params={"id": resource_id}, stream=True
    )
    token = _get_confirm_token(response)

    if token:
        params = {"id": resource_id, "confirm": token}
        response = session.get(google_drive_download_url, params=params, stream=True)

    return _save_response_content(response)


def _get_confirm_token(response):
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            return value

    return None


CHUNK_SIZE = 32768


def _save_response_content(response) -> bytes:
    content_bytes = b""
    max_file_size = get_max_file_size()
    for chunk in response.iter_content(CHUNK_SIZE):
        if not chunk:  # filter out keep-alive new chunks
            continue
        content_bytes += chunk
        if len(content_bytes) >= max_file_size:
            raise Exception("Content on Google Drive too large.")
    return content_bytes


def get_notebook_from_google_drive_or_colaboratory(url: str):
    resource_id = get_resource_id_from_url(url)
    if resource_id is None:
        raise Exception(f"Could not get resource id from url: {url}")

    # DEBUG
    print(resource_id)
    maybe_json_bytes = get_file_from_google_drive_by_requests(resource_id)

    maybe_json_str = str(maybe_json_bytes, encoding="utf_8")
    return maybe_json_str
