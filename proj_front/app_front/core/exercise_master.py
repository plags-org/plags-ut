import dataclasses
import datetime
import enum
import io
import json
import os
import subprocess
import tempfile
import traceback
import zipfile
from typing import Any, Dict, List, Literal, Optional, Tuple, Union, final, get_args

import requests
from django.contrib import messages
from django.core.files.uploadedfile import UploadedFile
from django.http.request import HttpRequest
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from pydantic.error_wrappers import ValidationError
from typing_extensions import TypeAlias, TypeGuard

from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.forms import UploadExerciseForeachCourseForm, UploadExerciseForm
from app_front.models import (
    Course,
    Exercise,
    ExerciseVersion,
    Organization,
    UserAuthorityEnum,
)
from app_front.utils.exception_util import (
    SystemLogicalError,
    SystemResponsibleException,
    UserResponsibleException,
)
from app_front.utils.notebook_util import read_as_notebook
from app_front.utils.parameter_decoder import from_user_timezone
from app_front.utils.time_util import get_current_datetime

# from extension.pydantic_strict import StrictBaseModel as BaseModel
from .judge_metadata import PlagsJudgeMasterNotebookMetadata
from .judge_util import get_judger_url
from .plags_utils.request_user import get_request_user_safe
from .storage_util import save_upload_file
from .types import (
    ColaboratoryResourceID,
    ErrorMessage,
    Failure,
    IsSuccess,
    String64,
    StringUrl64,
    Success,
    assert_Optional_ColaboratoryResourceID_convert,
)


class ExerciseMasterUploadFileFormat(enum.Enum):
    ZIPPED = "ZIPPED"


def detect_exercise_master_upload_file_format(
    upload_file_name: str,
) -> ExerciseMasterUploadFileFormat:
    """課題マスタの更新ファイルに対し、形式検知を行う。

    ありうる可能性:
    - *.zip     -> ZIP形式 (autograde.zip, as-is_master.zip)
    """
    if upload_file_name.endswith(".zip"):
        return ExerciseMasterUploadFileFormat.ZIPPED
    raise ValueError(upload_file_name)


class MetadataError(UserResponsibleException):
    pass


def _drop_notebook_judge_master_metadata(master_notebook_json: str) -> str:
    nb_json = json.loads(master_notebook_json)
    if "metadata" not in nb_json:
        return master_notebook_json
    if "judge_master" not in nb_json["metadata"]:
        return master_notebook_json
    del nb_json["metadata"]["judge_master"]
    return json.dumps(nb_json, ensure_ascii=False, indent=1)


_UserVisibleFromType: TypeAlias = Literal["student", "assistant", "lecturer", None]


def assert_UserVisibleFromType(some: Any) -> TypeGuard[_UserVisibleFromType]:
    assert some in get_args(_UserVisibleFromType), f"{some} is not UserVisibleFromType"
    return True


ERROR_MESSAGE__LECTURER_RESPONSIBLE = _("Submitted configuration file is broken")
ERROR_MESSAGE__SYSTEM_RESPONSIBLE = _(
    "Internal error occurred. If this continues, please contact the system admin."
)

ExerciseNameToConcreteHashTable = Dict[str, str]


@dataclasses.dataclass
class ExerciseMasterUploadOptions:
    overwrite_title: bool
    overwrite_deadlines: bool
    overwrite_drive: bool
    overwrite_shared_after_confirmed: bool
    overwrite_confidentiality: bool
    as_draft: bool
    overwrite_draft: bool
    overwrite_trial: bool


@dataclasses.dataclass
class JudgeMasterMetadataDeadlines:
    begins_at: Optional[datetime.datetime]
    opens_at: Optional[datetime.datetime]
    checks_at: Optional[datetime.datetime]
    closes_at: Optional[datetime.datetime]
    ends_at: Optional[datetime.datetime]


@dataclasses.dataclass
class TrialOptions:
    enabled: bool

    initial_source: str
    editor_name: str
    editor_options: Optional[str]


@dataclasses.dataclass
class JudgeMasterMetadata:
    autograde: bool
    deadlines: JudgeMasterMetadataDeadlines
    drive: Optional[ColaboratoryResourceID]
    exercise_name: StringUrl64
    score_visible_from: Optional[UserAuthorityEnum]
    remarks_visible_from: Optional[UserAuthorityEnum]
    shared_after_confirmed: Optional[bool]
    title: String64
    version: String64
    trial_options: TrialOptions

    @final
    @classmethod
    def from_notebook_metadata(
        cls, notebook_metadata: PlagsJudgeMasterNotebookMetadata
    ) -> "JudgeMasterMetadata":
        trial_editor_name = "CodeMirror"
        trial_options = TrialOptions(
            enabled=False,
            initial_source="",
            editor_name=trial_editor_name,
            editor_options=None,
        )
        if notebook_metadata.trial is not None:
            trial_options = TrialOptions(
                enabled=True,
                initial_source=notebook_metadata.trial.initial_source,
                editor_name=notebook_metadata.trial.editor.name,
                editor_options=json.dumps(
                    notebook_metadata.trial.editor.options,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            )
        return JudgeMasterMetadata(
            autograde=notebook_metadata.evaluation,
            deadlines=JudgeMasterMetadataDeadlines(
                begins_at=notebook_metadata.deadlines.begin,
                opens_at=notebook_metadata.deadlines.open,
                checks_at=notebook_metadata.deadlines.check,
                closes_at=notebook_metadata.deadlines.close,
                ends_at=notebook_metadata.deadlines.end,
            ),
            drive=assert_Optional_ColaboratoryResourceID_convert(
                notebook_metadata.drive
            ),
            exercise_name=notebook_metadata.name,
            score_visible_from=_parse_optional_user_authority_enum(
                notebook_metadata.confidentiality.score
            ),
            remarks_visible_from=_parse_optional_user_authority_enum(
                notebook_metadata.confidentiality.remarks
            ),
            shared_after_confirmed=notebook_metadata.shared_after_confirmed,
            title=notebook_metadata.title,
            version=notebook_metadata.version,
            trial_options=trial_options,
        )


def _parse_optional_user_authority_enum(
    user_authority_key: Optional[str],
) -> Optional[UserAuthorityEnum]:
    if user_authority_key is None:
        return None
    return {auth.name.lower(): auth for auth in UserAuthorityEnum}[user_authority_key]


def _convert_optional_user_authority_to_str(
    user_authority: Optional[UserAuthorityEnum],
) -> Optional[str]:
    if user_authority is None:
        return None
    return user_authority.value


def _parse_notebook_judge_master_metadata(
    master_notebook_json: str,
) -> JudgeMasterMetadata:
    """`master_notebook_json` から `JudgeMasterMetadata` を作成する

    - cf. `PlagsJudgeMasterNotebookMetadata`
    """
    try:
        master_notebook = read_as_notebook(master_notebook_json)
    except ValueError:
        assert False, "Invalid Jupyter Notebook"

    try:
        metadata = master_notebook.metadata

        # 旧 judge_master 形式のメタデータからの互換性は捨て、弾く
        if "judge_master" in metadata:
            raise AssertionError('Legacy metadata format (~2022, "judge_master").')

        if "plags" not in metadata:
            raise AssertionError(
                f'"plags" is required in metadata (found: {tuple(metadata)})'
            )
        plags_metadata = metadata["plags"]
        if not isinstance(plags_metadata, dict):
            raise AssertionError('metadata "plags" must be a JSON Object')

        try:
            notebook_metadata = PlagsJudgeMasterNotebookMetadata.parse_obj(
                plags_metadata
            )
        except ValidationError as exc:
            raise AssertionError(exc.json(indent=None)) from exc
        # parsed_legacy = JudgeMasterMetadata.parse(judge_master)
        # assert parsed_legacy == parsed
        parsed = JudgeMasterMetadata.from_notebook_metadata(notebook_metadata)
        return parsed

    except AssertionError as exc:
        traceback.print_exc()
        raise MetadataError(exc) from exc


def _is_current_or_new_version(exercise: Exercise, version: String64) -> bool:
    if exercise.latest_version == version:
        return True
    try:
        ExerciseVersion.objects.get(exercise=exercise, version=version)
        return False
    except ExerciseVersion.DoesNotExist:
        return True


def _create_or_update_exercise(
    request: HttpRequest,
    course: Course,
    judge_metadata: JudgeMasterMetadata,
    master_notebook_json: str,
    /,
    *,
    upload_options: ExerciseMasterUploadOptions,
    exercise_concrete_hash: Optional[str] = None,
) -> Tuple[IsSuccess, str]:
    request_user = get_request_user_safe(request)

    # NOTE 本当はここでユーザーのタイムゾーンではなくCourseのタイムゾーンを使うべき
    #      そうしないと教員のタイムゾーンが共有できていないと事故が発生する
    #     NOTE 現状、ユーザータイムゾーンは "Asia/Tokyo" 固定であるのでなんとかなっている
    user_timezone = request_user.timezone

    def _convert_if_valid(
        input_datetime: Optional[datetime.datetime],
    ) -> Optional[datetime.datetime]:
        if input_datetime is None:
            return None
        return from_user_timezone(user_timezone, input_datetime)

    begins_at = _convert_if_valid(judge_metadata.deadlines.begins_at)
    opens_at = _convert_if_valid(judge_metadata.deadlines.opens_at)
    checks_at = _convert_if_valid(judge_metadata.deadlines.checks_at)
    closes_at = _convert_if_valid(judge_metadata.deadlines.closes_at)
    ends_at = _convert_if_valid(judge_metadata.deadlines.ends_at)

    exercise: Exercise
    is_created: bool
    exercise, is_created = Exercise.objects.get_or_create(
        course=course,
        name=judge_metadata.exercise_name,
        defaults=dict(
            created_by=request_user,
            is_autograde=judge_metadata.autograde,
            latest_version=judge_metadata.version,
            latest_concrete_hash=exercise_concrete_hash,
            title=judge_metadata.title,
            body_ipynb_json=master_notebook_json,
            drive_resource_id=judge_metadata.drive,
            begins_at=begins_at,
            opens_at=opens_at,
            checks_at=checks_at,
            closes_at=closes_at,
            ends_at=ends_at,
            is_trial_enabled=judge_metadata.trial_options.enabled,
            trial_initial_source=judge_metadata.trial_options.initial_source,
            trial_editor_name=judge_metadata.trial_options.editor_name,
            trial_editor_options=judge_metadata.trial_options.editor_options,
            is_shared_after_confirmed=judge_metadata.shared_after_confirmed,
            score_visible_from=judge_metadata.score_visible_from,
            remarks_visible_from=judge_metadata.remarks_visible_from,
            is_draft=upload_options.as_draft,
            edited_by=request_user,
        ),
    )
    if is_created:
        ExerciseVersion.objects.get_or_create(
            exercise=exercise,
            version=judge_metadata.version,
            defaults=dict(created_by=request_user),
        )
        return Success, f'Exercise "{judge_metadata.exercise_name}" created.'

    changes_dict: Dict[str, Tuple[Any, Any]] = dict(
        is_autograde=(exercise.is_autograde, judge_metadata.autograde),
        latest_version=(exercise.latest_version, judge_metadata.version),
        latest_concrete_hash=(exercise.latest_concrete_hash, exercise_concrete_hash),
        body_ipynb_json=(exercise.body_ipynb_json, master_notebook_json),
    )
    if upload_options.overwrite_title:
        changes_dict.update(title=(exercise.title, judge_metadata.title))
    if upload_options.overwrite_deadlines:
        changes_dict.update(
            begins_at=(exercise.begins_at, begins_at),
            opens_at=(exercise.opens_at, opens_at),
            checks_at=(exercise.checks_at, checks_at),
            closes_at=(exercise.closes_at, closes_at),
            ends_at=(exercise.ends_at, ends_at),
        )
    if upload_options.overwrite_drive:
        changes_dict.update(
            drive_resource_id=(exercise.drive_resource_id, judge_metadata.drive)
        )
    if upload_options.overwrite_shared_after_confirmed:
        changes_dict.update(
            is_shared_after_confirmed=(
                exercise.is_shared_after_confirmed,
                judge_metadata.shared_after_confirmed,
            )
        )
    if upload_options.overwrite_confidentiality:
        changes_dict.update(
            score_visible_from=(
                exercise.score_visible_from,
                _convert_optional_user_authority_to_str(
                    judge_metadata.score_visible_from
                ),
            ),
            remarks_visible_from=(
                exercise.remarks_visible_from,
                _convert_optional_user_authority_to_str(
                    judge_metadata.remarks_visible_from
                ),
            ),
        )
    if upload_options.overwrite_draft:
        changes_dict.update(is_draft=(exercise.is_draft, upload_options.as_draft))
    if upload_options.overwrite_trial:
        changes_dict.update(
            is_trial_enabled=(
                exercise.is_trial_enabled,
                judge_metadata.trial_options.enabled,
            ),
            trial_initial_source=(
                exercise.trial_initial_source,
                judge_metadata.trial_options.initial_source,
            ),
            trial_editor_name=(
                exercise.trial_editor_name,
                judge_metadata.trial_options.editor_name,
            ),
            trial_editor_options=(
                exercise.trial_editor_options,
                judge_metadata.trial_options.editor_options,
            ),
        )

    updates = {
        key: (old, new) for key, (old, new) in changes_dict.items() if old != new
    }
    # print(list(updates))
    # print(updates)
    is_updated = bool(updates)

    if not is_updated:
        return Success, f'Exercise "{judge_metadata.exercise_name}" had no change.'

    if not _is_current_or_new_version(exercise, judge_metadata.version):
        return Failure, f'Exercise "{judge_metadata.exercise_name}" had old version.'

    if exercise.latest_version != judge_metadata.version:
        ExerciseVersion.objects.get_or_create(
            exercise=exercise,
            version=judge_metadata.version,
            defaults=dict(created_by=request_user),
        )

    exercise.is_autograde = judge_metadata.autograde
    exercise.latest_version = judge_metadata.version
    exercise.latest_concrete_hash = exercise_concrete_hash
    exercise.body_ipynb_json = master_notebook_json
    if upload_options.overwrite_title:
        exercise.title = judge_metadata.title
    if upload_options.overwrite_deadlines:
        exercise.begins_at = begins_at
        exercise.opens_at = opens_at
        exercise.checks_at = checks_at
        exercise.closes_at = closes_at
        exercise.ends_at = ends_at
    if upload_options.overwrite_drive:
        exercise.drive_resource_id = judge_metadata.drive
    if upload_options.overwrite_shared_after_confirmed:
        exercise.is_shared_after_confirmed = judge_metadata.shared_after_confirmed
    if upload_options.overwrite_confidentiality:
        exercise.score_visible_from = _convert_optional_user_authority_to_str(
            judge_metadata.score_visible_from
        )
        exercise.remarks_visible_from = _convert_optional_user_authority_to_str(
            judge_metadata.remarks_visible_from
        )
    if upload_options.overwrite_draft:
        exercise.is_draft = upload_options.as_draft
    if upload_options.overwrite_trial:
        exercise.is_trial_enabled = judge_metadata.trial_options.enabled
        exercise.trial_initial_source = judge_metadata.trial_options.initial_source
        exercise.trial_editor_name = judge_metadata.trial_options.editor_name
        exercise.trial_editor_options = judge_metadata.trial_options.editor_options
    exercise.edited_by = request_user
    exercise.edited_at = get_current_datetime()
    exercise.save()
    return (
        Success,
        f'Exercise "{judge_metadata.exercise_name}" updated ({", ".join(updates)}).',
    )


def _process_as_is_exercise(
    request: HttpRequest,
    course: Course,
    judge_metadata: JudgeMasterMetadata,
    master_notebook_json: str,
    /,
    *,
    upload_options: ExerciseMasterUploadOptions,
) -> Tuple[IsSuccess, str]:
    if judge_metadata.autograde is not False:
        return Failure, ERROR_MESSAGE__SYSTEM_RESPONSIBLE
    return _create_or_update_exercise(
        request,
        course,
        judge_metadata,
        master_notebook_json,
        upload_options=upload_options,
    )


def _create_exercise_concrete_upload_zip_bytes(
    judge_metadata: JudgeMasterMetadata, working_dir: str
) -> bytes:
    zip_dir = os.path.join(working_dir, judge_metadata.exercise_name + "__zip")
    zip_file = os.path.join(zip_dir, "uploaded.zip")
    os.makedirs(zip_dir)
    with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zip_f:
        exercise_concrete_dir = os.path.join(working_dir, judge_metadata.exercise_name)
        for dirpath, _dirnames, files in os.walk(exercise_concrete_dir):
            arc_dirpath = dirpath[len(os.path.join(exercise_concrete_dir, "")) :]
            for file in files:
                zip_f.write(
                    os.path.join(dirpath, file), os.path.join(arc_dirpath, file)
                )
    with open(zip_file, "rb") as zip_g:
        return zip_g.read()


def _send_concrete_to_judge_if_necessary(
    course: Course,
    judge_metadata: JudgeMasterMetadata,
    working_dir: str,
    exercise_concrete_hash: str,
) -> None:
    params = dict(
        agency_name="plags_ut_front",
        agency_department_name=f"{course.organization.name}__{course.name}",
        exercise_concrete_name=judge_metadata.exercise_name,
        exercise_concrete_version=judge_metadata.version,
        exercise_concrete_directory_hash=exercise_concrete_hash,
    )

    exists_uri = get_judger_url() + "/api/exercise_concrete/exists/"
    result = requests.get(exists_uri, params=params, timeout=0.5)
    if result.status_code != 200:
        raise SystemResponsibleException(
            f"Returned code is not [200] but [{result.status_code}]."
        )

    result_json = result.json()
    if result_json["result"]["exists"]:
        print(
            f"exercise {judge_metadata.exercise_name!r} already exists on judge side."
        )
        return
    zip_bytes = _create_exercise_concrete_upload_zip_bytes(judge_metadata, working_dir)
    files = dict(
        exercise_concrete_zip_file=(
            "uploaded.zip",
            zip_bytes,
            "application/octet-stream",
        ),
    )
    judger_uri = get_judger_url() + "/api/exercise_concrete/upload/"
    print(f"[INFO] insert_and_send_trial_evaluation: judger_uri: {judger_uri}")
    result = requests.post(judger_uri, data=params, files=files, timeout=1)
    result_json = result.json()
    print(f"response: {result_json!r}")
    if result_json["success"]:
        return
    raise UserResponsibleException("; ".join(result_json["reasons"]))


def _process_autograde_exercise(
    request: HttpRequest,
    course: Course,
    judge_metadata: JudgeMasterMetadata,
    master_notebook_json: str,
    working_dir: str,
    name_hash_table: ExerciseNameToConcreteHashTable,
    /,
    *,
    upload_options: ExerciseMasterUploadOptions,
) -> Tuple[IsSuccess, str]:
    if judge_metadata.autograde is not True:
        return Failure, ERROR_MESSAGE__SYSTEM_RESPONSIBLE

    if judge_metadata.exercise_name not in name_hash_table:
        raise UserResponsibleException(
            f'AutoEval exercise "{judge_metadata.exercise_name}"'
            " must have corresponding setting directory."
        )

    exercise_concrete_hash = name_hash_table[judge_metadata.exercise_name]
    _send_concrete_to_judge_if_necessary(
        course, judge_metadata, working_dir, exercise_concrete_hash
    )

    return _create_or_update_exercise(
        request,
        course,
        judge_metadata,
        master_notebook_json,
        upload_options=upload_options,
        exercise_concrete_hash=exercise_concrete_hash,
    )


def _process_notebook(
    request: HttpRequest,
    course: Course,
    judge_metadata: JudgeMasterMetadata,
    master_notebook_json: str,
    working_dir: str,
    name_hash_table: ExerciseNameToConcreteHashTable,
    /,
    *,
    upload_options: ExerciseMasterUploadOptions,
) -> Tuple[IsSuccess, str]:
    if judge_metadata.autograde:
        return _process_autograde_exercise(
            request,
            course,
            judge_metadata,
            master_notebook_json,
            working_dir,
            name_hash_table,
            upload_options=upload_options,
        )
    return _process_as_is_exercise(
        request,
        course,
        judge_metadata,
        master_notebook_json,
        upload_options=upload_options,
    )


def _get_exercise_concrete_directory_hash_table(
    working_dir: str,
) -> ExerciseNameToConcreteHashTable:
    try:
        command = (
            "git init && "
            "git add . && "
            'git -c user.name="foobar" -c user.email="foobar@example.com" commit -m FOOBAR'
        )
        subprocess.run(
            command,
            capture_output=True,
            check=True,
            shell=True,
            cwd=working_dir,
            encoding="utf_8",
        )

        # git ls-tree -d HEAD
        # > 040000 tree 55a040a5f97efc8a0a86f92c176a0f173e28633e	ex1-1-triangle
        result = subprocess.run(
            "git ls-tree -d HEAD .",
            capture_output=True,
            check=True,
            shell=True,
            cwd=working_dir,
            encoding="utf_8",
        )
        print("=" * 64)
        print(result.stdout)
        print("=" * 64)
        print(result.stderr)
        print("=" * 64)

        name_hash_table = {}
        for line in io.StringIO(result.stdout):
            # mode, object_type, object_hash, course_name
            # 040000 tree 477d2119003c47f677c31d581679dde90354fc3f    template
            _, _, object_hash, exercise_name = line.strip().split(maxsplit=3)
            name_hash_table[exercise_name] = object_hash
        return name_hash_table

    except Exception as exc:  # pylint: disable=broad-except
        raise SystemResponsibleException(exc) from exc


def process_zipped(
    request: HttpRequest,
    organization: Organization,
    course: Course,
    upload_file: UploadedFile,
    /,
    *,
    upload_options: ExerciseMasterUploadOptions,
) -> Tuple[IsSuccess, str]:
    success_messages: List[str] = []
    failure_messages: List[str] = []

    try:
        file_path = save_upload_file(
            upload_file, "exercise_upload", organization.name, course.name
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            # tmp_dir = os.path.join(
            #     settings.BASE_APP_DATA_DIR, '__debug__hoge', str(datetime.datetime.now().timestamp()))
            # os.makedirs(tmp_dir, exist_ok=True)
            with zipfile.ZipFile(file_path) as z_ipf:
                z_ipf.extractall(tmp_dir)

            notebook_files: List[str] = [
                notebook_file
                for notebook_file in os.listdir(tmp_dir)
                if os.path.isfile(os.path.join(tmp_dir, notebook_file))
                and notebook_file.endswith(".ipynb")
            ]

            name_hash_table = _get_exercise_concrete_directory_hash_table(tmp_dir)

            for notebook_file in sorted(notebook_files):
                print(f"notebook: {notebook_file}")
                try:
                    with open(
                        os.path.join(tmp_dir, notebook_file), encoding="utf_8"
                    ) as f_nb:
                        master_notebook_json = f_nb.read()
                    judge_metadata = _parse_notebook_judge_master_metadata(
                        master_notebook_json
                    )
                    exercise_body_ipynb_json = _drop_notebook_judge_master_metadata(
                        master_notebook_json
                    )

                    is_success, message = _process_notebook(
                        request,
                        course,
                        judge_metadata,
                        exercise_body_ipynb_json,
                        tmp_dir,
                        name_hash_table,
                        upload_options=upload_options,
                    )
                    if is_success:
                        success_messages.append(f"[File {notebook_file}] " + message)
                    else:
                        failure_messages.append(f"[File {notebook_file}] " + message)

                except UserResponsibleException as exc:
                    failure_messages.append(
                        f"[File {notebook_file}] " + exc.get_user_message()
                    )

    except requests.exceptions.ConnectionError:
        traceback.print_exc()
        message = "Failed to process uploaded file. (judge backend connection failure)"
        SLACK_NOTIFIER.error(message, tracebacks=traceback.format_exc())
        failure_messages.append(message)

    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        message = "Failed to process uploaded zip file."
        SLACK_NOTIFIER.error(message, tracebacks=traceback.format_exc())
        failure_messages.append(message)

    if failure_messages:
        return Failure, "\n* ".join(
            ["Batch update failed:"]
            + failure_messages
            + ["Exercises succeeded:"]
            + (success_messages or ["None"])
        )

    return Success, "\n* ".join(["Batch update successful:"] + success_messages)


class ErrorLevel(enum.Enum):
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    SUCCESS = "SUCCESS"


@dataclasses.dataclass
class Message:
    level: ErrorLevel
    message: ErrorMessage


@dataclasses.dataclass
class ImportExerciseMastersJobResult:
    is_successful: bool
    messages: List[Message] = dataclasses.field(default_factory=list)

    @staticmethod
    def make_error(error_message: ErrorMessage) -> "ImportExerciseMastersJobResult":
        return ImportExerciseMastersJobResult(
            is_successful=False,
            messages=[Message(level=ErrorLevel.ERROR, message=error_message)],
        )

    def add_prefix_to_messages(
        self, message_prefix: str
    ) -> "ImportExerciseMastersJobResult":
        for message in self.messages:
            message.message = message_prefix + message.message
        return self


def _to_job_result(is_successful: bool, message: str) -> ImportExerciseMastersJobResult:
    "過去のtuple形式の結果応答に対する緩衝レイヤ いずれ消す"
    level = ErrorLevel.SUCCESS if is_successful else ErrorLevel.ERROR
    return ImportExerciseMastersJobResult(
        is_successful=is_successful, messages=[Message(level=level, message=message)]
    )


def import_exercise_masters(
    request: HttpRequest,
    organization: Organization,
    course: Course,
    upload_file: UploadedFile,
    upload_options: ExerciseMasterUploadOptions,
) -> ImportExerciseMastersJobResult:
    try:
        # 形式判定
        try:
            upload_file_format = detect_exercise_master_upload_file_format(
                upload_file.name
            )
        except ValueError:
            messages.error(
                request,
                format_lazy(
                    "{}: {}",
                    ERROR_MESSAGE__LECTURER_RESPONSIBLE,
                    _("Invalid file format."),
                ),
            )
            return ImportExerciseMastersJobResult(is_successful=False)

        # 本処理
        if upload_file_format == ExerciseMasterUploadFileFormat.ZIPPED:
            is_successful, message = process_zipped(
                request,
                organization,
                course,
                upload_file,
                upload_options=upload_options,
            )
            return _to_job_result(is_successful, message)
        raise ValueError(upload_file_format)
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        message = "Failed to process uploaded file. (unexpected behavior)"
        SLACK_NOTIFIER.error(message, tracebacks=traceback.format_exc())
        return _to_job_result(Failure, ERROR_MESSAGE__SYSTEM_RESPONSIBLE)


def add_messages_to_request(request: HttpRequest, message_list: List[Message]) -> None:
    for message in message_list:
        if message.level in (ErrorLevel.CRITICAL, ErrorLevel.ERROR):
            messages.error(request, message.message)
        elif message.level == ErrorLevel.WARNING:
            messages.warning(request, message.message)
        elif message.level == ErrorLevel.INFO:
            messages.info(request, message.message)
        elif message.level == ErrorLevel.SUCCESS:
            messages.success(request, message.message)
        else:
            raise SystemLogicalError(f"Unexpected level: {message.level!r}")


def get_exercise_master_upload_options(
    form: Union[UploadExerciseForeachCourseForm, UploadExerciseForm]
) -> ExerciseMasterUploadOptions:
    if isinstance(form, UploadExerciseForeachCourseForm):
        return ExerciseMasterUploadOptions(
            overwrite_title=form.cleaned_data["overwrite_title"],
            overwrite_deadlines=form.cleaned_data["overwrite_deadlines"],
            overwrite_drive=form.cleaned_data["overwrite_drive"],
            overwrite_shared_after_confirmed=form.cleaned_data[
                "overwrite_shared_after_confirmed"
            ],
            overwrite_confidentiality=form.cleaned_data["overwrite_confidentiality"],
            as_draft=form.cleaned_data["as_draft"],
            overwrite_draft=form.cleaned_data["overwrite_draft"],
            overwrite_trial=True,
        )
    if isinstance(form, UploadExerciseForm):
        return ExerciseMasterUploadOptions(
            overwrite_title=True,
            overwrite_deadlines=form.cleaned_data["overwrite_deadlines"],
            overwrite_drive=True,
            overwrite_shared_after_confirmed=True,
            overwrite_confidentiality=True,
            as_draft=form.cleaned_data["as_draft"],
            # NOTE UIを変更しないように、これをTrueに固定することで意味を維持する
            overwrite_draft=True,
            overwrite_trial=True,
        )
    raise SystemLogicalError(f"Unexpected form type: {type(form)}")
