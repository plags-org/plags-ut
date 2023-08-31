import datetime
import io
import json
import traceback
from typing import Final, Literal, Optional

import dateutil.parser
import requests
from django.core.files.base import File

from app_front.config.config import APP_CONFIG
from app_front.core.types import Score
from app_front.dependency.system_notification import SLACK_NOTIFIER
from app_front.models import (
    Course,
    Exercise,
    Organization,
    Submission,
    SubmissionFormatEnum,
    SubmissionParcel,
    SubmissionTypeEnum,
    User,
)
from app_front.utils.time_util import get_current_datetime

_AGENCY_PLAGS_UT_FRONT: Final = "plags_ut_front"


def get_judger_url() -> str:
    return APP_CONFIG.JUDGE.ENDPOINT_URL


def insert_submission(
    organization: Organization,
    course: Course,
    exercise: Exercise,
    submitted_by: User,
    submission_source: str,
    submission_format: SubmissionFormatEnum,
    /,
    *,
    submission_parcel: Optional[SubmissionParcel] = None,
) -> Submission:
    # NOTE ここでのファイル名はDBに保存する際の便宜上のものであり、 Path traversal をくらわない限り何でも良い。
    #      judgeに受け渡す際にも何でもよく、judge側で提出設定に従って適切に改名されるものと考えて良い。
    #     cf. send_submission_to_judger
    submission_file = File(io.StringIO(submission_source), "submission.c")

    # id を確定させてから、その id のディレクトリにファイルを保存
    submission = Submission.objects.create(
        organization=organization,
        course=course,
        submission_parcel=submission_parcel,
        exercise=exercise,
        exercise_version=exercise.latest_version,
        exercise_concrete_hash=exercise.latest_concrete_hash,
        is_autograded_exercise=exercise.is_autograde,
        submitted_by=submitted_by,
        submission_format=submission_format.value,
    )
    submission.update_latest_flag_eventually()

    submission.submission_file = submission_file
    submission.save()

    return submission


def send_submission_to_judger(
    submission: Submission, /, *, submission_source: Optional[str] = None
) -> None:
    data = dict(
        agency_name=_AGENCY_PLAGS_UT_FRONT,
        agency_department_name=f"{submission.organization.name}__{submission.course.name}",
        exercise_concrete_name=submission.exercise.name,
        exercise_concrete_version=submission.exercise.latest_version,
        exercise_concrete_directory_hash=submission.exercise.latest_concrete_hash,
        token=APP_CONFIG.JUDGE.API_TOKEN,
        submission_id=submission.id,
    )

    if submission_source is None:
        with submission.submission_file.open("r") as file:
            submission_source = file.read()
    files = dict(
        submission_file=(
            "submission_file",
            bytes(submission_source, encoding="utf_8"),
            "application/octet-stream",
        )
    )

    judger_uri = get_judger_url() + "/api/submission/submit/"
    print(f"[INFO] send_submission_to_judger: judger_uri: {judger_uri}")
    try:
        result = requests.post(judger_uri, data=data, files=files, timeout=0.5)
        assert (
            result.status_code == 200
        ), f"Returned code is not [200] but [{result.status_code}]."

        result_json = result.json()
        external_submission_id = result_json["submission_id"]
        submission.external_submission_id = external_submission_id
        submission.evaluation_queued_at = get_current_datetime()
        submission.evaluation_progress_percent = 10
        submission.save()
        submission.refresh_from_db()

    except requests.exceptions.ConnectionError:
        traceback.print_exc()
        SLACK_NOTIFIER.critical(
            "Judge Connection Error", tracebacks=traceback.format_exc()
        )
    except AssertionError:
        traceback.print_exc()
        SLACK_NOTIFIER.critical("Judge API Error", tracebacks=traceback.format_exc())


def accepted_to_status(is_accepted: bool) -> Literal["AS", "FE"]:
    return "AS" if is_accepted else "FE"


def _deserialize_evaluated_at(evaluated_at: str) -> datetime.datetime:
    return dateutil.parser.isoparse(evaluated_at)


def _fetch_evaluation_from_judger(submission: Submission) -> None:
    params = dict(
        agency_name=_AGENCY_PLAGS_UT_FRONT,
        agency_department_name=f"{submission.organization.name}__{submission.course.name}",
        exercise_concrete_name=submission.exercise.name,
        exercise_concrete_version=submission.exercise_version,
        exercise_concrete_directory_hash=submission.exercise_concrete_hash,
        submission_id=submission.external_submission_id,
    )
    judger_uri = get_judger_url() + "/api/submission/result/"
    print(f"[INFO] _fetch_evaluation_from_judger: judger_uri: {judger_uri}")
    result = requests.get(judger_uri, params=params, timeout=0.5)
    assert (
        result.status_code == 200
    ), f"Returned code is not [200] but [{result.status_code}]."

    result_json = result.json()
    evaluation_result_json = result_json["evaluation_result_json"]

    # まだ評価結果が出ていない
    if not evaluation_result_json:
        return

    save_submission_evaluation_result_json(submission, evaluation_result_json)


def save_submission_evaluation_result_json(
    submission: Submission, evaluation_result_json: str
) -> None:
    evaluation_result = json.loads(evaluation_result_json)

    evaluated_at: datetime.datetime
    overall_grade: Optional[Score]
    overall_status: Literal["AS", "FE"]
    observed_statuses: str

    evaluator_version = evaluation_result["metadata"]["evaluator"]["version"]
    if evaluator_version == "v2.0":
        evaluated_at = _deserialize_evaluated_at(
            evaluation_result["metadata"]["evaluated_at"]
        )
        overall_grade = evaluation_result["overall_result"]["grade"]
        status_set = frozenset(evaluation_result["overall_result"]["status_set"])
        overall_status = "AS" if status_set == frozenset(("pass",)) else "FE"
        observed_statuses = json.dumps(evaluation_result["overall_result"]["tag_set"])
    else:
        raise ValueError(evaluator_version)

    # ただの複製（自作生成カラム）
    submission.evaluated_at = evaluated_at
    submission.evaluation_result_json = evaluation_result_json
    submission.overall_grade = overall_grade
    submission.overall_status = overall_status
    submission.observed_statuses = observed_statuses

    # これはオートメーション: overall_grade を lecturer_grade に自動で取込む（初期値とする）
    submission.lecturer_grade = overall_grade

    submission.save()
    submission.refresh_from_db()


def fetch_evaluation_result_if_necessary(
    submission: Submission,
    /,
    *,
    force: bool = False,
    # NOTE なんか使ってなさそうだが予定でもあったのだろうか...
    raise_on_failure: bool = False,
    notify_on_failure: bool = True,
) -> None:
    if not submission.is_autograded_exercise:
        return

    if submission.external_submission_id is None:
        send_submission_to_judger(submission)
        return

    if submission.is_evaluated():
        return

    try:
        _fetch_evaluation_from_judger(submission)
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        if notify_on_failure:
            SLACK_NOTIFIER.error(
                "Failed to fetch evaluation result from judger.", traceback.format_exc()
            )
        if raise_on_failure:
            raise


def insert_trial_submission(
    organization: Organization,
    course: Course,
    exercise: Exercise,
    submitted_by: User,
    submission_source: str,
) -> Submission:
    # NOTE ここでのファイル名はDBに保存する際の便宜上のものであり、 Path traversal をくらわない限り何でも良い。
    #      judgeに受け渡す際にも何でもよく、judge側で提出設定に従って適切に改名されるものと考えて良い。
    #     cf. send_submission_to_judger
    submission_file = File(io.StringIO(submission_source), "submission.py")

    # id を確定させてから、その id のディレクトリにファイルを保存
    trial_submission: Submission = Submission.objects.create(
        organization=organization,
        course=course,
        # submission_parcel=None (default)
        exercise=exercise,
        exercise_version=exercise.latest_version,
        exercise_concrete_hash=exercise.latest_concrete_hash,
        is_autograded_exercise=True,
        submitted_by=submitted_by,
        # submission_format=SubmissionFormatEnum.PYTHON_SOURCE.value (default)
        submission_type=SubmissionTypeEnum.TRIAL,
        # NOTE トライアル提出は常に最新提出として扱わない
        #      最新提出フラグは NORMAL 内での利用を想定するため
        is_latest_submission=False,
    )

    trial_submission.submission_file = submission_file
    trial_submission.save()

    return trial_submission
