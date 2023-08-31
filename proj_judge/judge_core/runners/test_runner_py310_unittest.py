"""テストステージを実行し結果を返却する

ATTENTION 実装上の注意点

* Python >= 3.10 で動作する必要がある
  * `dataclasses` は利用可能
  * `typing.Self` は利用できない
* 標準モジュールのみで実現する必要がある
  * `typing_extensions` は利用できない
  * `pydantic` は利用できない
  * `colorama` は利用できない
"""
import argparse
import dataclasses
import enum
import json
import logging
import os
import signal
import subprocess
import sys
import traceback
from typing import Any, NoReturn, Union

SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SOURCE_DIR, "../.."))

# pylint: disable=wrong-import-position
from judge_core.common.parameter_serializer import decode_parameter  # noqa:E402
from judge_core.common.runner_interface import (  # noqa:E402
    BuiltinEvaluationTag,
    ResultTypeCode,
    TestCaseResultData,
    TestStageResult,
    get_colored_evaluation_tags,
)

_logger = logging.getLogger(__file__)
LOGGER_FORMATTER = logging.Formatter(
    "%(asctime)s %(msecs)03d\t%(process)d\t%(thread)d\t"
    "%(filename)s:%(lineno)d\t%(funcName)s\t"
    "%(levelname)s\t%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S %z (%Z)",
)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
stream_handler.setFormatter(LOGGER_FORMATTER)
_logger.addHandler(stream_handler)


def _valid_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


@dataclasses.dataclass
class RunnerOptions:
    exercise_concrete_dir: str
    state_name: str
    evaluation_dir: str
    evaluation_filename: str
    evaluation_result_filename: str
    options: str
    log_level: str = "ERROR"
    dry_run: bool = False

    def __post_init__(self) -> None:
        # NOTE Pydanticが使えないかわりにvalidatorを自作する

        # e.g. 'evaluations/123456/precheck'
        if not _valid_str(self.evaluation_dir):
            raise ValueError("RunnerOptions: option `evaluation_dir` is reqired")
        # e.g. 'evaluations/123456'
        if not _valid_str(self.evaluation_filename):
            raise ValueError("RunnerOptions: option `evaluation_filename` is reqired")
        # e.g. 'evaluations/123456/output_result.json'
        if not _valid_str(self.evaluation_result_filename):
            raise ValueError(
                "RunnerOptions: option `evaluation_result_filename` is reqired"
            )


PYTHON_COMMAND = "python"

KEY_EVALUATION_STYLE = "evaluation_style"

STATE_UNITTEST_FILENAME = os.path.basename(__file__)

SEPARATOR_70_EQ = (
    "======================================================================"
)
SEPARATOR_70_HP = (
    "----------------------------------------------------------------------"
)

STATUS_CODE_OFFSET = 192

# 呼び出し側責任
STATUS_CODE_INVALID_ARGUMENT_LIST = STATUS_CODE_OFFSET - 4
STATUS_CODE_NO_SUCH_EXERCISE_DIRECTORY = STATUS_CODE_OFFSET - 8
STATUS_CODE_INVALID_SETTING = STATUS_CODE_OFFSET - 10

# Runner責任
STATUS_CODE_FAILED_TO_PREPARE_SUBMISSION_SOURCE = STATUS_CODE_OFFSET + 12
STATUS_CODE_FAILED_TO_EVAL_TEST = STATUS_CODE_OFFSET + 16
STATUS_CODE_NO_SUCH_SOURCE_FILE = STATUS_CODE_OFFSET + 20
STATUS_CODE_FAILED_TO_EVAL_SOURCE = STATUS_CODE_OFFSET + 24
STATUS_CODE_FAILED_TO_GET_FUNC = STATUS_CODE_OFFSET + 28
STATUS_CODE_INVALID_TEST_CASE = STATUS_CODE_OFFSET + 32
STATUS_CODE_FAILED_TO_GET_JUDGE_GRADE = STATUS_CODE_OFFSET + 36
STATUS_CODE_FAILED_TO_DUMP_JUDGE_RESULTS = STATUS_CODE_OFFSET + 40
STATUS_CODE_FAILED_TO_WRITE_JUDGE_RESULTS = STATUS_CODE_OFFSET + 44

STATUS_CODE_FAILED_TO_GET_TEST_FUNCNAME = STATUS_CODE_OFFSET + 48
STATUS_CODE_FAILED_TO_GET_TEST_CASES = STATUS_CODE_OFFSET + 50
STATUS_CODE_FAILED_TO_GET_TEST_EXECUTOR = STATUS_CODE_OFFSET + 52
STATUS_CODE_FAILED_TO_GET_TEST_GRADER = STATUS_CODE_OFFSET + 54

STATUS_CODE_TEST_RUNNER_FAILED_UNEXPECTEDLY = STATUS_CODE_OFFSET + 63


_LogLevel = int


def _log_subprocess_result(
    logger: logging.Logger,
    log_level: _LogLevel,
    result: Union["subprocess.CompletedProcess[str]", subprocess.CalledProcessError],
) -> None:
    logger.log(log_level, "============ [%s] ==== <stdout> %s", __file__, "=" * 64)
    logger.log(log_level, result.stdout)
    logger.log(log_level, "============ [%s] ==== <stderr> %s", __file__, "=" * 64)
    logger.log(log_level, result.stderr)
    logger.log(log_level, "============ [%s] ==== <------> %s", __file__, "=" * 64)


class EvaluationStyle(str, enum.Enum):
    SEPARATE = "separate"
    APPEND = "append"

    def is_separate(self) -> bool:
        return self == self.SEPARATE

    def is_append(self) -> bool:
        return self == self.APPEND


class _ResultManager:
    def __init__(self) -> None:
        self._case_result_list: TestStageResult = []

    def add_result(self, case_result: TestCaseResultData) -> None:
        self._case_result_list.append(case_result)
        states_str = get_colored_evaluation_tags(case_result.tags)
        _logger.info(
            f"{states_str} {case_result.name} => {str(case_result.msg)!r}"
            f" ({str(case_result.err)!r})"
        )

    def terminate(self, evaluation_result_filepath: str) -> NoReturn:
        if evaluation_result_filepath == "None":
            sys.exit()

        try:
            result_list = [res.dict() for res in self._case_result_list]
            json_str_oneline = json.dumps(result_list)
            json_str = json.dumps(result_list, indent=4)
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            sys.exit(STATUS_CODE_FAILED_TO_DUMP_JUDGE_RESULTS)

        try:
            with open(evaluation_result_filepath, "w", encoding="utf_8") as f_er:
                f_er.write(json_str)
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc()
            sys.exit(STATUS_CODE_FAILED_TO_WRITE_JUDGE_RESULTS)

        print(file=sys.stderr)
        print(json_str_oneline, file=sys.stderr, end="")
        sys.exit()


def _run_test(options: RunnerOptions) -> None:
    _logger.setLevel(options.log_level)
    _logger.info("options = %r", options)

    # e.g. 'pre1-1-fermat_number', 'given'
    exercise_concrete_dir = options.exercise_concrete_dir
    state_name = options.state_name

    if not os.path.isdir(exercise_concrete_dir):
        _logger.error("No directory named `%s` .", exercise_concrete_dir)
        sys.exit(STATUS_CODE_NO_SUCH_EXERCISE_DIRECTORY)

    # e.g. 'submissions/12345/given'
    evaluation_dir = options.evaluation_dir
    evaluation_filename = options.evaluation_filename

    # e.g. '{...}': JSON string
    try:
        runner_options = json.loads(decode_parameter(options.options))
        _logger.debug(f"runner_options={runner_options}")
        assert KEY_EVALUATION_STYLE in runner_options
        evaluation_style = EvaluationStyle(runner_options[KEY_EVALUATION_STYLE])
    except (json.JSONDecodeError, AssertionError, ValueError):
        _logger.exception(f"runner_options={runner_options}")
        sys.exit(STATUS_CODE_INVALID_SETTING)

    # e.g. 'evaluation_result_given.json'
    evaluation_result_filepath = os.path.join(
        evaluation_dir, options.evaluation_result_filename + ".json"
    )

    # NOTE this should be the responsibility of the caller (test_runner.py)
    evaluation_dir = os.path.join(evaluation_dir, state_name)
    if not os.path.isdir(evaluation_dir):
        raise Exception(
            f"evaluation_dir is not a directory: {evaluation_dir!r} ({os.getcwd()=})"
        )

    ################################################################
    _logger.info("Preparation phase start")
    submission_path = os.path.join(evaluation_dir, evaluation_filename)
    unittest_path = os.path.join(exercise_concrete_dir, state_name + ".py")
    state_unittest_path = os.path.join(evaluation_dir, STATE_UNITTEST_FILENAME)
    try:
        if evaluation_style.is_separate():
            with open(unittest_path, encoding="utf_8") as test, open(
                state_unittest_path, "w", encoding="utf_8"
            ) as dst:
                dst.write(test.read())
        elif evaluation_style.is_append():
            with open(submission_path, encoding="utf_8") as src, open(
                unittest_path, encoding="utf_8"
            ) as test, open(state_unittest_path, "w", encoding="utf_8") as dst:
                dst.write(
                    "\n\n".join(
                        (
                            src.read(),
                            "## submission above, state test cases below",
                            test.read(),
                        )
                    )
                )
    except Exception:  # pylint: disable=broad-except
        _logger.exception("Preparation phase failed")
        sys.exit(STATUS_CODE_FAILED_TO_PREPARE_SUBMISSION_SOURCE)

    ################################################################
    _logger.info("Evaluation phase start")
    result_manager = _ResultManager()
    is_intended_break = False
    try:
        command = (PYTHON_COMMAND, STATE_UNITTEST_FILENAME)
        # NOTE sandbox のデバッグ時にのみ利用する 本番にリリースしてはいけない
        # command = ('strace', '-qcf', ) + command
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            encoding="utf_8",
            cwd=evaluation_dir,
        )

        _log_subprocess_result(_logger, logging.DEBUG, result)

        if result.returncode == signal.SIGKILL.value:
            # killed by SIGKILL (almost certainly by timeout)
            is_intended_break = True
            _log_subprocess_result(_logger, logging.DEBUG, result)
            result_manager.add_result(
                TestCaseResultData(
                    name="(Entire stage)",
                    status=ResultTypeCode.ERROR,
                    tags=[BuiltinEvaluationTag.TLE],
                    msg="",
                    err=result.stderr,
                    system_message="",
                )
            )
            raise Exception()

        if result.returncode != 0:
            # Python が exit(N) する場合にここを通る。
            is_intended_break = True
            _log_subprocess_result(_logger, logging.INFO, result)
            result_manager.add_result(
                TestCaseResultData(
                    name="(Entire stage)",
                    status=ResultTypeCode.ERROR,
                    tags=[BuiltinEvaluationTag.UA],
                    msg="",
                    err=result.stderr,
                    system_message="",
                )
            )
            raise Exception(
                f"[ERROR] {BuiltinEvaluationTag.UA.name} on {state_name},"
                f" result.returncode was {result.returncode}."
            )

        _logger.debug(result.stdout)
        try:
            lines = result.stdout.rstrip("\n").split("\n")
            output_json_line = lines[-1]
            case_result_dict_list = json.loads(output_json_line)
            assert isinstance(case_result_dict_list, list)
            for case_result_dict in case_result_dict_list:
                result_manager.add_result(
                    TestCaseResultData.parse_obj(case_result_dict)
                )
        except Exception:  # pylint: disable=broad-except
            result_manager.add_result(
                TestCaseResultData(
                    name="(system: parsing output)",
                    status=ResultTypeCode.FATAL,
                    tags=[BuiltinEvaluationTag.ESE],
                    msg="",
                    err="Failed to parse case output: " + result.stdout,
                    system_message=traceback.format_exc(),
                )
            )
    except Exception:  # pylint: disable=broad-except
        if not is_intended_break:
            traceback.print_exc()
            result_manager.add_result(
                TestCaseResultData(
                    name="(Entire stage)",
                    status=ResultTypeCode.ERROR,
                    tags=[BuiltinEvaluationTag.UA],
                    msg="",
                    err="Runner raised unknown exception.",
                    system_message=traceback.format_exc(),
                )
            )

    result_manager.terminate(evaluation_result_filepath)


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "exercise_concrete_dir",
        type=str,
        help="directory containing target ExerciseConcrete",
    )
    parser.add_argument("state_name", type=str, help="name of current state")
    parser.add_argument(
        "evaluation_dir", type=str, help="directory containing a submission"
    )
    parser.add_argument(
        "evaluation_filename", type=str, help="file containing a submission"
    )
    parser.add_argument(
        "evaluation_result_filename", type=str, help="result JSON file name"
    )
    parser.add_argument("options", type=str, help="test options for target state")
    parser.add_argument(
        "-l", "--log_level", type=str, default="ERROR", help="log level"
    )
    parser.add_argument("-r", "--dry_run", action="store_true", help="dry-run option")
    parsed_args = parser.parse_args()

    parsed_options = RunnerOptions(
        exercise_concrete_dir=parsed_args.exercise_concrete_dir,
        state_name=parsed_args.state_name,
        evaluation_dir=parsed_args.evaluation_dir,
        evaluation_filename=parsed_args.evaluation_filename,
        evaluation_result_filename=parsed_args.evaluation_result_filename,
        options=parsed_args.options,
        log_level=parsed_args.log_level,
        dry_run=parsed_args.dry_run,
    )

    try:
        _run_test(parsed_options)
    except Exception:  # pylint: disable=broad-except
        traceback.print_exc()
        sys.exit(STATUS_CODE_TEST_RUNNER_FAILED_UNEXPECTEDLY)


if __name__ == "__main__":
    _main()
