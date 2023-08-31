"""
状態遷移と下位ランナーの呼び出し、自動評価結果の取りまとめを担当する
"""
import argparse
import logging
import os
from typing import Final, Optional

from typing_extensions import TypeAlias

from judge_core.evaluators.common import EvaluationOptions
from judge_core.evaluators.evaluator_v2 import EvaluationResponseV2, EvaluatorV2
from judge_core.exercise_concrete.exercise_loader import (
    ExerciseConcrete,
    load_exercise_concrete,
)
from judge_core.exercise_concrete.schema_v1_0.schema import (
    SCHEMA_VERSION as SCHEMA_VERSION_v1_0,
)
from judge_core.exercise_concrete.schema_v1_0.schema import Setting as SettingV1_0

_LOGGER_FORMATTER: Final = logging.Formatter(
    "%(asctime)s %(msecs)03d\t%(process)d\t%(thread)d\t"
    "%(filename)s:%(lineno)d\t%(funcName)s\t"
    "%(levelname)s\t%(message)s",
    datefmt="%Y-%m-%d %H:%M:%S %z (%Z)",
)

_DEBUG_LOG_FILE: Final = "evaluation.debug.log"
_ERROR_LOG_FILE: Final = "evaluation.error.log"


def set_stream_logger(logger: logging.Logger, options: EvaluationOptions) -> None:
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(options.log_level)
    stream_handler.setFormatter(_LOGGER_FORMATTER)
    logger.addHandler(stream_handler)


def set_file_logger(logger: logging.Logger, options: EvaluationOptions) -> None:
    debug_file_handler = logging.FileHandler(
        os.path.join(options.evaluation_dir, _DEBUG_LOG_FILE)
    )
    debug_file_handler.setLevel(logging.DEBUG)
    debug_file_handler.setFormatter(_LOGGER_FORMATTER)
    logger.addHandler(debug_file_handler)

    error_file_handler = logging.FileHandler(
        os.path.join(options.evaluation_dir, _ERROR_LOG_FILE)
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.setFormatter(_LOGGER_FORMATTER)
    logger.addHandler(error_file_handler)


EvaluationResponseType: TypeAlias = EvaluationResponseV2


def evaluate(
    options: EvaluationOptions,
    exercise_concrete: ExerciseConcrete,
    /,
    *,
    logger: Optional[logging.Logger] = None,
) -> EvaluationResponseType:
    if logger is None:
        logger = logging.getLogger(__file__)
    logger.setLevel(options.log_level)

    # 自動評価環境の初期化
    os.makedirs(options.evaluation_dir, exist_ok=True)
    set_file_logger(logger, options)

    # alias setting in use
    setting = exercise_concrete.setting
    if exercise_concrete.schema_version == SCHEMA_VERSION_v1_0:
        assert isinstance(setting, SettingV1_0), setting
        return EvaluatorV2(setting).evaluate(options, logger=logger)
    raise AssertionError(exercise_concrete.schema_version)


def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "exercise_concrete_dir",
        type=str,
        help="directory containing target ExerciseConcrete",
    )
    parser.add_argument(
        "submission_dir",
        type=str,
        help="directory containing a submission, existing one (readonly)",
    )
    parser.add_argument(
        "submission_filename",
        type=str,
        help="submission file, in `{{ submission_dir }}/` (readonly)",
    )
    parser.add_argument(
        "evaluation_dir",
        type=str,
        help="directory containing an evaluation, created by me",
    )
    parser.add_argument(
        "evaluation_result_filename", type=str, help="output JSON file name"
    )
    parser.add_argument(
        "-l", "--log_level", type=str, default="ERROR", help="log level"
    )
    parser.add_argument("-r", "--dry_run", action="store_true", help="dry-run option")
    parsed_args = parser.parse_args()

    parsed_options = EvaluationOptions(
        exercise_concrete_dir=parsed_args.exercise_concrete_dir,
        submission_dir=parsed_args.submission_dir,
        submission_filename=parsed_args.submission_filename,
        evaluation_dir=parsed_args.evaluation_dir,
        evaluation_result_filename=parsed_args.evaluation_result_filename,
        log_level=parsed_args.log_level,
        dry_run=parsed_args.dry_run,
    )
    exercise_concrete = load_exercise_concrete(parsed_options.exercise_concrete_dir)

    main_logger = logging.getLogger(__file__)
    set_stream_logger(main_logger, parsed_options)
    evaluate(parsed_options, exercise_concrete, logger=main_logger)


if __name__ == "__main__":
    _main()
