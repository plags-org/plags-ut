import datetime
import json
import os
import shutil
from typing import Union

from django.conf import settings
from django.core.files.uploadedfile import UploadedFile

from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.utils.console_message import TEE_DEV_NULL, Tee


def save_upload_file(upload_file: UploadedFile, *additional_path: str) -> str:
    external_data_base_path = os.path.join(
        settings.BASE_APP_DATA_DIR, "external_data", *additional_path
    )
    os.makedirs(external_data_base_path, exist_ok=True)
    external_data_file_name = (
        f"{datetime.datetime.now().timestamp()}__{upload_file.name}"
    )
    external_data_file_path = os.path.join(
        external_data_base_path, external_data_file_name
    )
    with open(external_data_file_path, "wb") as f:
        f.write(upload_file.read())
        upload_file.seek(0)
    return external_data_file_path


def save_error_json_file(notebook: dict, external_subdir: str, filename: str) -> str:
    error_files_dir = os.path.join(
        settings.BASE_APP_DATA_DIR, "external_data", external_subdir
    )
    os.makedirs(error_files_dir, exist_ok=True)
    error_file_name = f"{datetime.datetime.now().timestamp()}__{filename}"
    error_file_path = os.path.join(error_files_dir, error_file_name)
    with open(error_file_path, "w", encoding="utf_8") as file:
        json.dump(notebook, file, ensure_ascii=False, indent=1)
    return error_file_path


def save_error_text_file(
    notebook_str: Union[str, bytes], external_subdir: str, filename: str
) -> str:
    error_files_dir = os.path.join(
        settings.BASE_APP_DATA_DIR, "external_data", external_subdir
    )
    os.makedirs(error_files_dir, exist_ok=True)
    error_file_name = f"{datetime.datetime.now().timestamp()}__{filename}"
    error_file_path = os.path.join(error_files_dir, error_file_name)
    if isinstance(notebook_str, str):
        with open(error_file_path, "w", encoding="utf_8") as file:
            file.write(notebook_str)
    elif isinstance(notebook_str, bytes):
        with open(error_file_path, "wb") as bin_file:
            bin_file.write(notebook_str)
    else:
        SLACK_NOTIFIER.critical(
            f"Unexpected type: {type(notebook_str)=}, {notebook_str=!r}"
        )
    return error_file_path


def remove_all_files_uploaded_via_save_upload_file(
    *additional_path: str, tee: Tee = TEE_DEV_NULL, verbose: bool = False
) -> None:
    """
    `save_upload_file` によってアップロードされたファイルを削除する

    NOTE 呼び出し元ごとに別の `additional_path` が指定されていれば、機能単位でごっそり消せて良い
    """
    external_data_base_path = os.path.join(
        settings.BASE_APP_DATA_DIR, "external_data", *additional_path
    )
    remove_all_files_in_path(external_data_base_path, tee=tee, verbose=verbose)


def remove_all_files_in_path(
    target_path: str, *, tee: Tee = TEE_DEV_NULL, verbose: bool = False
) -> None:
    """
    特定ディレクトリ以下のファイルを削除する

    `shutil.rmtree` のwrapperであるが `data_migration` 向けのログ出力をサポートしている
    """
    # IDEA 間違った場合にも復元できるようにtarを作っておく?
    #      どこに置くかが難しいのでやめた
    #      `shutil.make_archive()` and `tarfile.TarFile().getmembers()`
    total_capacity = 0
    for root, _dirs, files in os.walk(target_path):
        capacity = sum(os.path.getsize(os.path.join(root, name)) for name in files)
        tee.info(
            root, "consumes", capacity, "bytes in", len(files), "non-directory files"
        )
        total_capacity += capacity
    tee.info("Cleaning", total_capacity, "bytes in total")
    if verbose:
        tee.info("shutil.rmtree skipped (verbose=True)")
        return
    tee.info("shutil.rmtree start")
    shutil.rmtree(target_path)
    tee.info("shutil.rmtree successful")
