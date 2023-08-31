import dataclasses
import datetime
import enum
import os
import traceback
from typing import TypedDict

import django_rq
import httpx
from django.conf import settings
from django.utils import timezone

from app_judge.models import Submission
from judge_core.common.runner_interface import BuiltinEvaluationTag
from judge_core.common.types_ import DirectoryPathString
from judge_core.evaluator import EvaluationResponseType, evaluate
from judge_core.evaluators.common import EvaluationOptions, MissConfigurationError
from judge_core.evaluators.evaluator_v2 import (
    EvaluationResponseMetadataEvaluatorModel,
    EvaluationResponseMetadataExerciseConcreteModel,
    EvaluationResponseMetadataModel,
    EvaluationResponseV2,
    EvaluationTagModel,
    OverallResult,
    StatusEnum,
)
from judge_core.exercise_concrete.exercise_loader import load_exercise_concrete
from judge_core.exercise_concrete.schema_loader import SchemaVersion
from judge_core.exercise_concrete.schema_v1_0.schema import (
    SCHEMA_VERSION as SCHEMA_VERSION_v1_0,
)

# global submission queue
submission_queue = django_rq.get_queue(settings.SUBMISSION_QUEUE_NAME)


def get_exercise_concrete_base_dir(
    agency_name: str,
    agency_department_name: str,
    exercise_concrete_name: str,
    exercise_concrete_version: str,
    exercise_concrete_directory_hash: str,
) -> DirectoryPathString:
    return os.path.join(
        settings.EXTERNAL_DATA_PATH,
        "exercise_concretes",
        agency_name,
        agency_department_name,
        exercise_concrete_name,
        exercise_concrete_version,
        exercise_concrete_directory_hash,
    )


def get_exercise_concrete_dir(
    agency_name: str,
    agency_department_name: str,
    exercise_concrete_name: str,
    exercise_concrete_version: str,
    exercise_concrete_directory_hash: str,
) -> DirectoryPathString:
    return os.path.join(
        settings.EXTERNAL_DATA_PATH,
        "exercise_concretes",
        agency_name,
        agency_department_name,
        exercise_concrete_name,
        exercise_concrete_version,
        exercise_concrete_directory_hash,
        "raw",
    )


def is_exercise_concrete_exists(
    agency_name: str,
    agency_department_name: str,
    exercise_concrete_name: str,
    exercise_concrete_version: str,
    exercise_concrete_directory_hash: str,
) -> bool:
    exercise_concrete_dir = get_exercise_concrete_dir(
        agency_name,
        agency_department_name,
        exercise_concrete_name,
        exercise_concrete_version,
        exercise_concrete_directory_hash,
    )
    return os.path.isdir(exercise_concrete_dir)


def get_evaluation_dir(submission_id: int) -> DirectoryPathString:
    return os.path.join(
        settings.EXTERNAL_DATA_PATH, "evaluation_results", str(submission_id)
    )


class _EvaluateFailureTypeEnum(str, enum.Enum):
    ESE = "ESE"
    BSE = "BSE"


def _get_failure_evaluation_response(
    failure_type: _EvaluateFailureTypeEnum, *, version: SchemaVersion
) -> EvaluationResponseType:
    if version == SCHEMA_VERSION_v1_0:
        return _get_failure_evaluation_response_v1(failure_type)
    raise AssertionError(version)


def _failure_type_to_evaluation_tag(
    failure_type: _EvaluateFailureTypeEnum,
) -> EvaluationTagModel:
    if failure_type == _EvaluateFailureTypeEnum.ESE:
        return EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.ESE)
    if failure_type == _EvaluateFailureTypeEnum.BSE:
        return EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.BSE)
    raise AssertionError(failure_type)


def _get_failure_evaluation_response_v1(
    failure_type: _EvaluateFailureTypeEnum,
) -> EvaluationResponseV2:
    return EvaluationResponseV2(
        metadata=EvaluationResponseMetadataModel(
            submission_key="TBD",
            evaluation_key="TBD",
            evaluated_at=datetime.datetime.now(datetime.timezone.utc),
            exercise_concrete=EvaluationResponseMetadataExerciseConcreteModel(
                name="__placeholder__",
                version="__placeholder__",
                directory_hash="__placeholder__",
            ),
            evaluator=EvaluationResponseMetadataEvaluatorModel(
                name="__placeholder__",
                version="__placeholder__",
            ),
        ),
        state_history=[],
        state_results={},
        overall_result=OverallResult(
            status_set=[StatusEnum.FATAL],
            grade=None,
            time=None,
            memory=None,
            tag_set=[_failure_type_to_evaluation_tag(failure_type)],
        ),
    )


@dataclasses.dataclass
class EvaluationInfo:
    agency_name: str
    agency_department_name: str
    exercise_concrete_name: str
    exercise_concrete_version: str
    exercise_concrete_directory_hash: str
    submission_id: int
    submission_file_name: str


def _validate_options(options: EvaluationOptions) -> None:
    # e.g. 'pre1-1-fermat_number'

    # e.g. 'submissions/123456', 'submissions/123456/output_result.json'
    assert options.submission_dir != "", "[ERROR] option `submission_dir` is required"
    assert (
        options.evaluation_result_filename != ""
    ), "[ERROR] option `evaluation_result_filename` is required"


def evaluation_func(evaluation_info: EvaluationInfo) -> None:
    print(
        "[DEBUG]",
        f"{{{evaluation_info.submission_id}}}",
        "<job_in_submission_queue>",
        len(submission_queue),
    )
    submission_id = evaluation_info.submission_id

    try:
        exercise_concrete_dir = get_exercise_concrete_dir(
            evaluation_info.agency_name,
            evaluation_info.agency_department_name,
            evaluation_info.exercise_concrete_name,
            evaluation_info.exercise_concrete_version,
            evaluation_info.exercise_concrete_directory_hash,
        )
        evaluation_dir = get_evaluation_dir(submission_id)

        options = EvaluationOptions(
            exercise_concrete_dir=exercise_concrete_dir,
            submission_dir=settings.MEDIA_ROOT,
            submission_filename=evaluation_info.submission_file_name,
            evaluation_dir=evaluation_dir,
            evaluation_result_filename="evaluation_result",
            log_level="DEBUG",
        )
        _validate_options(options)
        exercise_concrete = load_exercise_concrete(options.exercise_concrete_dir)

        try:
            evaluation_response: EvaluationResponseType = evaluate(
                options, exercise_concrete
            )
        except MissConfigurationError:
            traceback.print_exc()
            evaluation_response = _get_failure_evaluation_response(
                _EvaluateFailureTypeEnum.ESE, version=exercise_concrete.schema_version
            )
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            evaluation_response = _get_failure_evaluation_response(
                _EvaluateFailureTypeEnum.BSE, version=exercise_concrete.schema_version
            )

    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        evaluation_response = _get_failure_evaluation_response(
            _EvaluateFailureTypeEnum.ESE, version=SCHEMA_VERSION_v1_0
        )

    assert isinstance(evaluation_response, EvaluationResponseV2)
    metadata_concrete_v2 = evaluation_response.metadata.exercise_concrete
    metadata_concrete_v2.name = evaluation_info.exercise_concrete_name
    metadata_concrete_v2.version = evaluation_info.exercise_concrete_version
    metadata_concrete_v2.directory_hash = (
        evaluation_info.exercise_concrete_directory_hash
    )

    metadata_evaluator_v2 = evaluation_response.metadata.evaluator
    metadata_evaluator_v2.name = "plags_ut_judge"
    metadata_evaluator_v2.version = "v2.0"

    grade = evaluation_response.overall_result.grade
    time = evaluation_response.overall_result.time
    memory = evaluation_response.overall_result.memory
    print(evaluation_response.json(indent=4, ensure_ascii=False))
    print(
        f"[DEBUG] {{{evaluation_info.submission_id}}} evaluation complete"
        f" [ {grade} / {time} / {memory} ]."
    )

    evaluation_result_json = evaluation_response.json()

    # データベース更新
    submission = Submission.objects.get(id=submission_id)
    submission.evaluated_at = timezone.now()
    submission.evaluation_result_json = evaluation_result_json
    submission.save()

    # 評価完了を front へ通知
    judge_reply_json_dict = {
        "submission_id": submission.front_submission_id,
        "token": settings.JUDGE_API_TOKEN,
        "progress": 100,
        "evaluation_result_json": evaluation_result_json,
    }

    front_endpoint_url: str = settings.JUDGE_FRONT_ENDPOINT_URL

    client_args: _ClientKwargDict = {}
    if settings.JUDGE_FRONT_USE_UNIX_DOMAIN_SOCKET:
        # Unix domain socket を経由するので HTTPS -> HTTP 化する
        if front_endpoint_url.startswith("https://"):
            front_endpoint_url = "http://" + front_endpoint_url[len("https://") :]
        transport = httpx.HTTPTransport(uds="/run/gunicorn.sock")
        client_args = {"transport": transport}

    with httpx.Client(**client_args) as client:
        result = client.post(
            front_endpoint_url,
            json=judge_reply_json_dict,
        )
        print("Reply-back:", result.status_code, result.text)


class _ClientKwargDict(TypedDict, total=False):
    transport: httpx.HTTPTransport
