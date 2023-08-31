import io
import json
import traceback
from typing import List, Optional, Tuple, Union

import nbformat
from django.core.files.base import File
from django.db import IntegrityError, transaction
from django.http.request import HttpRequest
from django.utils.translation import gettext_lazy as _
from pydantic import ValidationError

from app_front.config.config import APP_CONFIG
from app_front.core.judge_metadata import PlagsJudgeSubmissionNotebookMetadata
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import SubmitSubmissionParcelForm
from app_front.models import (
    Course,
    Exercise,
    Organization,
    SubmissionFormatEnum,
    SubmissionParcel,
)
from app_front.utils.exception_util import (
    SystemResponsibleException,
    UserResponsibleException,
)

from .google_drive.google_drive_api import (
    GoogleDriveResourceNotFound,
    GoogleDriveResourceTooLarge,
    get_file_from_google_drive,
)
from .google_drive.utils import get_resource_id_from_url
from .judge_util import insert_submission, send_submission_to_judger
from .plags_utils.request_user import get_request_user_safe
from .storage_util import save_error_json_file, save_error_text_file


def _extract_submission_from_parcel(exercise: Exercise, parcel_ipynb_json: dict) -> str:
    """提出された Notebook の中から、課題に対応する提出コードを抽出する

    - cf. 最新の仕様: <https://github.com/plags-org/plags_ut_dev/issues/396>
    """
    try:
        matched_cell_sources = []
        assert "cells" in parcel_ipynb_json and isinstance(
            parcel_ipynb_json["cells"], list
        ), "cells (Array) is required"
        for cell in parcel_ipynb_json["cells"]:
            assert "cell_type" in cell, "cells[N].cell_type (String) is required"
            if cell["cell_type"] != "code":
                continue
            metadata = cell.get("metadata", {})
            if (
                metadata.get("name") == f"answer_cell:{exercise.name}"
                and metadata.get("deletable") is False
            ):
                source = "".join(cell["source"])
                matched_cell_sources.append(source)

        assert len(matched_cell_sources) != 0, "No answer cell found"
        assert len(matched_cell_sources) == 1, "Multiple answer cells found"
        return matched_cell_sources[0]

    except AssertionError as exc:
        error_json_filename = save_error_json_file(
            parcel_ipynb_json,
            "submission_parcels_error_files",
            "extract_submission_from_parcel",
        )
        raise UserResponsibleException(
            exc, exercise_name=exercise.name, error_json_filename=error_json_filename
        ) from exc

    except Exception as exc:  # pylint: disable=broad-except
        error_json_filename = save_error_json_file(
            parcel_ipynb_json,
            "submission_parcels_error_files",
            "extract_submission_from_parcel",
        )
        raise SystemResponsibleException(
            exc, exercise_name=exercise.name, error_json_filename=error_json_filename
        ) from exc


def extract_submissions_from_parcel_if_necessary(
    course: Course, parcel_ipynb_json_str: str, parcel_ipynb_resource_name: str
) -> Tuple[Tuple[Exercise, SubmissionFormatEnum, str], ...]:
    """
    ipp: {
     "metadata": {
      "judge_submission": {
       "exercises": {
        "pre2-1-between": "e8069133c347d6146f58c4f705590e5b65ae0acf",
        "pre2-2-inc_digits": "e8069133c347d6146f58c4f705590e5b65ae0acf"
       },
       "extraction": true
      }
     },
    }

    ppp: {
     "metadata": {
      "judge_submission": {
       "exercises": {
        "ex1-1": "2020SS"
       },
       "extraction": false
      }
     },
    }

    返り値が
    - エラー → 例外送出
    - 成功   → Tuple[Tuple[Exercise, SubmissionFormatEnum, str], ...]
    """
    try:
        # print(parcel_ipynb_json_str)
        notebook = json.loads(parcel_ipynb_json_str)
        # 一度 notebook として読み込んでみることで形式違反を弾く
        nbformat.reads(parcel_ipynb_json_str, nbformat.NO_CONVERT)

    except (json.JSONDecodeError, ValueError) as exc:
        error_text_filename = save_error_text_file(
            parcel_ipynb_json_str,
            "submission_parcels_error_files",
            "extract_submissions_from_parcel_if_necessary",
        )

        key_phrases = (
            "Google ドライブなら、無料でファイルをバックアップして携帯電話、タブレット、パソコンから手軽にアクセスできます。",
            "まずは、15 GB の無料の Google ストレージをご利用ください。",
            "<title>Google ドライブ - 1 か所であらゆるファイルを保管</title>",
        )
        if sum(phrase in parcel_ipynb_json_str for phrase in key_phrases) >= 2:
            raise UserResponsibleException(
                str(
                    _(
                        "Submitted file %(filename)s cannot be read by PLAGS UT. "
                        'Probably you forgot to share the notebook to "Anyone with the link".'  # noqa:E501
                    )
                    % dict(filename=parcel_ipynb_resource_name)
                ),
                error_text_filename=error_text_filename,
            ) from exc

        raise UserResponsibleException(
            str(
                _(
                    "Submitted file %(filename)s is not a valid Jupyter Notebook document."  # noqa:E501
                )
                % dict(filename=parcel_ipynb_resource_name)
            ),
            error_text_filename=error_text_filename,
        ) from exc
    except Exception as exc:
        # 想定外の形式エラー（発生して妥当そうなら上に追記すること）
        error_text_filename = save_error_text_file(
            parcel_ipynb_json_str,
            "submission_parcels_error_files",
            "extract_submissions_from_parcel_if_necessary",
        )
        raise SystemResponsibleException(
            str(
                _(
                    "Submitted file %(filename)s is not a valid Jupyter Notebook document."  # noqa:E501
                )
                % dict(filename=parcel_ipynb_resource_name)
            ),
            error_text_filename=error_text_filename,
        ) from exc

    # nbformat的には正当な形式のNotebookファイルであることが確認されたことになる

    try:
        assertion_message: str = "metadata (Object) is required"
        assert isinstance(notebook, dict) and "metadata" in notebook, assertion_message
        metadata = notebook["metadata"]
        assert isinstance(metadata, dict), assertion_message

        assertion_message = 'Legacy metadata format (~2022, "judge_submission").'
        assert "judge_submission" not in metadata, assertion_message

        assertion_message = "metadata.plags (Object) is required"
        assert "plags" in metadata, assertion_message
        plags_metadata = metadata["plags"]
        assert isinstance(plags_metadata, dict), assertion_message

        try:
            notebook_metadata = PlagsJudgeSubmissionNotebookMetadata.parse_obj(
                plags_metadata
            )
        except ValidationError as exc:
            raise AssertionError(exc.json(indent=None)) from exc

    except AssertionError as exc:
        error_text_filename = save_error_text_file(
            parcel_ipynb_json_str,
            "submission_parcels_error_files",
            "extract_submissions_from_parcel_if_necessary",
        )
        raise UserResponsibleException(
            str(
                _(
                    "Submitted file %(filename)s has metadata error (%(message)s). "
                    "It seems that you have submitted an ipynb file not based on a distributed one."  # noqa:E501
                )
                % dict(filename=parcel_ipynb_resource_name, message=str(exc))
            ),
            error_text_filename=error_text_filename,
        ) from exc

    # plags_ut的にも正当な形式のNotebookファイルであることが確認された

    submissions: List[Tuple[Exercise, SubmissionFormatEnum, str]] = []
    try:
        validation_errors: List[Union[str, UserResponsibleException]] = []

        # exercisesが空なものは意味的に意図不明なので設定不良として落とす
        if not notebook_metadata.exercises:
            validation_errors.append("No exercises found in submission metadata.")

        for name, version in notebook_metadata.exercises.items():
            # check if such exercise really exists, with correct version
            if not isinstance(name, str):
                validation_errors.append(f"Exercise name must be string: got {name=!r}")
                continue
            if version is not None and not isinstance(version, str):
                validation_errors.append(
                    f"Exercise version must be null or string: got {version=!r}"
                )
                continue
            try:
                exercise = Exercise.objects.get(course=course, name=name)
            except Exercise.DoesNotExist:
                validation_errors.append(f"Exercise not found: {name=}")
                continue
            # NOTE version is None は「バージョンの検査を行わない」を意味する
            if version is not None and exercise.latest_version != version:
                validation_errors.append(
                    f"Exercise Version Mismatch: {version=}, {exercise.latest_version=}"
                )
                continue

            if notebook_metadata.extraction:
                try:
                    extracted_notebook = _extract_submission_from_parcel(
                        exercise, notebook
                    )
                except UserResponsibleException as exc:
                    validation_errors.append(exc)
                    continue
                submissions.append(
                    (
                        exercise,
                        SubmissionFormatEnum(SubmissionFormatEnum.PYTHON_SOURCE),
                        extracted_notebook,
                    )
                )
            else:
                submissions.append(
                    (
                        exercise,
                        SubmissionFormatEnum(SubmissionFormatEnum.JUPYTER_NOTEBOOK),
                        json.dumps(notebook),
                    )
                )

        if validation_errors:
            raise UserResponsibleException(
                [
                    str(
                        _(
                            "Submission file content error. "
                            "Perhaps you submitted a wrong file or edited some part where you should not."  # noqa:E501
                        )
                    )
                ]
                + validation_errors
            )

    except KeyError as exc:
        raise UserResponsibleException(
            str(
                _(
                    "Submitted file is not a valid Jupyter Notebook document for this course."  # noqa:E501
                )
            )
        ) from exc

    except AssertionError as exc:
        raise UserResponsibleException(
            str(
                _(
                    "Submitted Jupyter Notebook file is outdated. "
                    "Please check out the latest Notebook provided by the lecturer."
                )
            )
        ) from exc

    return tuple(submissions)


def process_submission_parcel(
    request: HttpRequest,
    organization: Organization,
    course: Course,
    form: SubmitSubmissionParcelForm,
) -> SubmissionParcel:
    """
    SubmissionParcel の提出を処理する

    成功 → SubmissionParcel を返す
    失敗 → PlagsBaseException を返す
    """
    submission_colaboratory_url = form.cleaned_data["submission_colaboratory_url"]
    submission_parcel_file = form.cleaned_data["submission_parcel_file"]

    # どちらか一方のみ指定することを要求する
    if not any((submission_colaboratory_url, submission_parcel_file)):
        raise UserResponsibleException(
            str(_("Set your colaboratory shared URL or your local file to submit."))
        )
    if sum(map(bool, (submission_colaboratory_url, submission_parcel_file))) > 1:
        raise UserResponsibleException(
            str(_("Choose one from colaboratory shared URL or local file to submit."))
        )

    # 提出方法による場合分け
    if submission_colaboratory_url:
        resource_id = get_resource_id_from_url(submission_colaboratory_url)
        if resource_id is None:
            raise UserResponsibleException(
                str(
                    _(
                        "Unable to parse file resource id from url. Please check that the URL is correct."  # noqa:E501
                    )
                ),
                submission_colaboratory_url=submission_colaboratory_url,
            )
        try:
            file_data = get_file_from_google_drive(
                resource_id,
                APP_CONFIG.GOOGLE_DRIVE.FILE_DOWNLOAD_METHOD,
                fallbacks=APP_CONFIG.GOOGLE_DRIVE.FILE_DOWNLOAD_METHOD_FALLBACKS,
            )
        except GoogleDriveResourceNotFound as exc:
            raise UserResponsibleException(
                str(
                    _(
                        "Unable to get notebook from cloud. "
                        "Please check that the URL is correct, the notebook is in sharing state."  # noqa:E501
                    )
                ),
                submission_colaboratory_url=submission_colaboratory_url,
            ) from exc
        except GoogleDriveResourceTooLarge as exc:
            raise UserResponsibleException(
                str(exc)
                + ": "
                + str(
                    _(
                        "Notebook file on cloud too large. "
                        "Please check that the file contains only expected contents."
                    )
                ),
                submission_colaboratory_url=submission_colaboratory_url,
            ) from exc
        google_drive_json_str = file_data.content
        filename = file_data.name
        maybe_submissions = extract_submissions_from_parcel_if_necessary(
            course, google_drive_json_str, filename
        )

    if submission_parcel_file:
        if not submission_parcel_file.name.endswith(".ipynb"):
            raise UserResponsibleException(
                str(_("Submission must be of Jupyter Notebook format (*.ipynb)."))
            )
        try:
            submission_parcel_file_content = str(
                submission_parcel_file.read(), encoding="utf_8"
            )
        except UnicodeDecodeError as exc:
            raise UserResponsibleException(
                str(
                    _(
                        "Submitted file must be encoded with UTF-8. "
                        "Probably you created a notebook file in a wrong way."
                    )
                )
            ) from exc
        maybe_submissions = extract_submissions_from_parcel_if_necessary(
            course, submission_parcel_file_content, submission_parcel_file.name
        )

    # valid SubmissionParcel submission.

    # 提出期限の確認
    exercise: Exercise
    submission_format: SubmissionFormatEnum
    submission_source: str

    unaccepted_delays: List[Tuple[str, str]] = []
    for exercise, _submission_format, _submission_source in maybe_submissions:
        if not exercise.opens():
            unaccepted_delays.append((exercise.title, "not opened yet"))
        elif exercise.closes():
            unaccepted_delays.append((exercise.title, "already closed"))

    if unaccepted_delays:
        raise UserResponsibleException(
            ", ".join(
                f"{exercise_title} ({reason})"
                for exercise_title, reason in unaccepted_delays
            )
        )

    submissions_to_judge = []
    try:
        request_user = get_request_user_safe(request)

        with transaction.atomic():
            # SubmissionParcel を作成
            # NOTE id を確定させてから、その id のディレクトリにファイルを保存する必要がある
            submission_parcel = SubmissionParcel.objects.create(
                organization=organization,
                course=course,
                submitted_by=request_user,
            )
            if submission_colaboratory_url:
                submission_parcel.submission_parcel_file = File(
                    io.StringIO(google_drive_json_str), "submission_parcel.ipynb"
                )
                submission_parcel.submission_colaboratory_url = (
                    submission_colaboratory_url
                )
                submission_parcel.submission_parcel_file_initial_name = filename
            if submission_parcel_file:
                submission_parcel.submission_parcel_file = File(
                    submission_parcel_file, "submission_parcel.ipynb"
                )
                submission_parcel.submission_parcel_file_initial_name = (
                    submission_parcel_file.name
                )
            submission_parcel.save()

            # Submission を作成
            for exercise, submission_format, submission_source in maybe_submissions:
                submission = insert_submission(
                    organization,
                    course,
                    exercise,
                    request_user,
                    submission_source,
                    submission_format,
                    submission_parcel=submission_parcel,
                )
                if exercise.is_autograde:
                    submissions_to_judge.append(submission)

    except IntegrityError as exc:
        raise SystemResponsibleException(exc) from exc

    # 提出をjudgeに送り自動評価をトリガする
    for submission in submissions_to_judge:
        try:
            send_submission_to_judger(submission)
        except Exception:  # pylint: disable=broad-except
            # NOTE 提出レコード（Submission）自体はすでにできているので、Judgeで障害が発生していても、
            #      回復するまで待ってから再送すればよいので、提出操作自体をエラーとする必要はない。
            SLACK_NOTIFIER.error(
                "Failed to send submission to judger.", traceback.format_exc()
            )
            traceback.print_exc()

    return submission_parcel


def workaround_supply_default_file_name(file_name: Optional[str]) -> str:
    if not file_name:
        file_name = "submission.ipynb"
    elif not file_name.endswith(".ipynb"):
        file_name += ".ipynb"
    return file_name
