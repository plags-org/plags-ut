import datetime
import enum
import functools
import json
import logging
import math
import os
import shutil
import signal
import subprocess
from abc import abstractmethod
from typing import (
    Dict,
    Final,
    FrozenSet,
    Generic,
    List,
    Optional,
    Protocol,
    Tuple,
    TypeVar,
)

from pydantic import BaseModel, ConstrainedStr
from typing_extensions import TypeAlias

from judge_core.common.limitrace_util import (
    get_stderr_result_json_limitrace_resource_statistics,
)
from judge_core.common.parameter_serializer import encode_parameter
from judge_core.common.runner_interface import (
    SYSTEM_FAILURE_TAG_NAME_SET,
    BuiltinEvaluationTag,
    EvaluationTagData,
)
from judge_core.common.types_ import DirectoryPathString, FileName
from judge_core.exercise_concrete.common.schema_type import (
    CustomStateName,
    StateName,
    String64,
    String1024,
    StringAscii256,
)
from judge_core.exercise_concrete.schema_v1_0.schema import Grade
from judge_core.exercise_concrete.schema_v1_0.schema import Setting as SettingV0_2
from judge_core.exercise_concrete.schema_v1_0.schema import (
    SettingJudgeEvaluationState,
    SettingJudgeEvaluationStateRunner,
)

from .common import (
    EnvironmentOptions,
    EvaluationOptions,
    FirejailOptions,
    LimitraceOptions,
    MissConfigurationError,
    get_environment_list,
    log_subprocess_result,
    time_limit_to_microseconds,
)
from .const import (
    ENVIRONMENT_ROOT,
    FIREJAIL_FAILURE_CODE,
    PYTHON_COMMAND,
    STATUS_CODE_OFFSET,
    TEST_RUNNER_DIR,
)


class _SchemaBaseModel(BaseModel):
    # class Config:
    #     extra = "forbid"
    pass


################################################################
# runnerとの間でのインターフェイス


class HtmlColorString(ConstrainedStr):
    min_length = 4
    max_length = 7
    regex = r"^#([0-9a-fA-F]{3}){1,2}$"


class EvaluationTagModel(_SchemaBaseModel):
    name: str
    description: str
    background_color: HtmlColorString
    font_color: HtmlColorString
    visible: bool

    class Config:
        frozen = True

    def __lt__(self, lhs: "EvaluationTagModel") -> bool:
        if not isinstance(lhs, EvaluationTagModel):
            raise NotImplementedError
        return self._sort_key() < lhs._sort_key()

    def _sort_key(self) -> Tuple[str, str, HtmlColorString, HtmlColorString, bool]:
        return (
            self.name,
            self.description,
            self.background_color,
            self.font_color,
            self.visible,
        )

    @classmethod
    def from_dataclass(cls, data: EvaluationTagData) -> "EvaluationTagModel":
        return EvaluationTagModel.parse_obj(data.dict())


@enum.unique
class StatusEnum(str, enum.Enum):
    PASS = "pass"  # 正解相当
    FAIL = "fail"  # テスト実行が正常に失敗（単に出力がおかしい等）
    ERROR = "error"  # テスト実行が異常終了
    FATAL = "fatal"  # 上記以外（テスト実行以前のトラブル等）

    @staticmethod
    @functools.lru_cache(1)
    def _mapping_display_order() -> Dict["StatusEnum", int]:
        return {
            StatusEnum.PASS: 50,
            StatusEnum.ERROR: 40,
            StatusEnum.FAIL: 30,
            StatusEnum.FATAL: 20,
        }

    def to_display_order(self) -> int:
        return self._mapping_display_order()[self]


class StateCaseResultModel(_SchemaBaseModel):
    name: CustomStateName
    status: StatusEnum
    tags: List[EvaluationTagModel]
    msg: str  # message欄に出力すべき文字列
    err: str  # unittest.main が生成するstack backtrace
    system_message: str


################################################################
# 上位evaluatorとの間でのインターフェイス


class EvaluationResponseMetadataExerciseConcreteModel(BaseModel):
    name: String64
    version: String64
    directory_hash: String64


class EvaluationResponseMetadataEvaluatorModel(BaseModel):
    name: String64
    version: String64


class EvaluationResponseMetadataModel(BaseModel):
    submission_key: StringAscii256
    evaluation_key: StringAscii256
    evaluated_at: datetime.datetime
    exercise_concrete: EvaluationResponseMetadataExerciseConcreteModel

    evaluator: EvaluationResponseMetadataEvaluatorModel


class StateRunnerModel(BaseModel):
    name: str
    version: str

    @classmethod
    def parse_state_runner(
        cls, state_runner: SettingJudgeEvaluationStateRunner
    ) -> "StateRunnerModel":
        return StateRunnerModel(
            name=state_runner.name,
            version=state_runner.version,
        )


class StateCaseResult(BaseModel):
    name: String64
    status: StatusEnum
    tags: List[EvaluationTagModel]
    student_message: String1024
    reviewer_message: String1024
    system_message: String1024

    @classmethod
    def from_runner_result(cls, result: StateCaseResultModel) -> "StateCaseResult":
        return StateCaseResult(
            name=result.name,
            status=result.status,
            tags=result.tags,
            student_message=result.msg,
            reviewer_message=result.err,
            system_message=result.system_message,
        )


class ResultModel(BaseModel):
    status_set: List[StatusEnum]
    time: Optional[int]
    memory: Optional[int]
    tag_set: List[EvaluationTagModel]


class StateResultModel(BaseModel):
    runner: StateRunnerModel
    cases: List[StateCaseResult]
    result: ResultModel


class OverallResult(BaseModel):
    status_set: List[StatusEnum]
    grade: Optional[Grade]
    time: Optional[int]
    memory: Optional[int]
    tag_set: List[EvaluationTagModel]


class EvaluationResponseV2(BaseModel):
    metadata: EvaluationResponseMetadataModel

    state_history: List[StateName]
    state_results: Dict[StateName, StateResultModel]

    overall_result: OverallResult


_TEvaluationResponse_co = TypeVar(
    "_TEvaluationResponse_co", bound=BaseModel, covariant=True
)


class EvaluatorProtocol(Protocol, Generic[_TEvaluationResponse_co]):
    @abstractmethod
    def evaluate(
        self, options: EvaluationOptions, logger: logging.Logger
    ) -> _TEvaluationResponse_co:
        raise NotImplementedError


class Base64String(ConstrainedStr):
    # cf. <https://stackoverflow.com/questions/475074/regex-to-parse-or-validate-base64-data> # noqa:E501
    regex = r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$"


class StateEvaluateArgsModel(BaseModel):
    state_runner_path: DirectoryPathString
    evaluation_filename: FileName
    runner_options_json_b64: Base64String
    time_limit_second: int


class EvaluationFailureException(Exception):
    "TestStateの実行に失敗"

    def __init__(self, tag_set: List[EvaluationTagModel]) -> None:
        super().__init__(())
        self.tag_set = tag_set


TransitionSpec: TypeAlias = Tuple[CustomStateName, Optional[Grade]]


class EvaluatorV2(EvaluatorProtocol[EvaluationResponseV2]):
    def __init__(self, setting: SettingV0_2) -> None:
        super().__init__()
        self._setting = setting

        environment = self._setting.judge.environment
        environment_name = environment.name
        environment_version = environment.version
        assert environment_name in get_environment_list(), environment_name
        assert environment_version == "", environment_version
        self._environment_options = EnvironmentOptions(
            ENVIRONMENT_ROOT, environment_name, environment_version
        )

        # NOTE 現状これ以外実装されていない
        assert self._setting.judge.sandbox.name in (
            "Firejail",
            "NsJail",
        ), self._setting.judge.sandbox.name
        self._sandbox_options = FirejailOptions(
            self._setting.judge.sandbox.options.dict()
        )

        self._limitrace_options = LimitraceOptions()

    def evaluate(
        self, options: EvaluationOptions, logger: logging.Logger
    ) -> EvaluationResponseV2:
        ################################################
        # 自動評価ミーリマシン実行
        state_results: Dict[StateName, StateResultModel] = {}
        state_name: StateName = self._setting.judge.evaluation.initial_state
        state_history: List[StateName] = []
        overall_grade: Optional[Grade] = None
        while state_name != "$":  # "$" は終了状態を表す予約名
            logger.debug(f"Now {state_name=}")
            state_history.append(state_name)

            state = self._setting.judge.evaluation.states[state_name]

            ################################################
            # 自動評価前準備
            try:
                evaluate_args = self._preprocess(options, logger, state_name, state)
            except MissConfigurationError as exc:
                # 設定異常があるので強制中断する
                logger.error("State terminated by miss-configuration", exc_info=True)
                state_tags = [
                    EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.ESE)
                ]
                state_results[state_name] = StateResultModel(
                    runner=StateRunnerModel.parse_state_runner(state.runner),
                    cases=[
                        StateCaseResult(
                            name="__setup__",
                            status=StatusEnum.FATAL,
                            tags=state_tags,
                            student_message="",
                            reviewer_message=exc.error_message,
                            system_message="",
                        )
                    ],
                    result=ResultModel(
                        status_set=[StatusEnum.FATAL],
                        time=None,
                        memory=None,
                        tag_set=state_tags,
                    ),
                )
                break

            try:
                result = self._evaluate_state(
                    options, logger, state_name, evaluate_args
                )
            except EvaluationFailureException as exc:
                # 制御下にない異常が起きているので強制中断する
                state_results[state_name] = StateResultModel(
                    runner=StateRunnerModel.parse_state_runner(state.runner),
                    cases=[],
                    result=ResultModel(
                        status_set=[StatusEnum.FATAL],
                        time=None,
                        memory=None,
                        tag_set=exc.tag_set,
                    ),
                )
                break

            state_result: List[StateCaseResultModel] = []

            # this means no runtime failures.
            (
                _stderr_remain,
                resource_usage,
                _limit_detection,
            ) = get_stderr_result_json_limitrace_resource_statistics(result)

            # TLE, MLE を検出・報告する
            if (
                resource_usage.time_elapse_nsec
                >= time_limit_to_microseconds(state.time_limit) * 1000
            ):
                state_result.append(
                    StateCaseResultModel(
                        name="(Entire stage)",
                        status=StatusEnum.ERROR,
                        tags=[
                            EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.TLE)
                        ],
                        msg="",
                        err="",
                        system_message="",
                    )
                )
            if resource_usage.ru_maxrss >= self._sandbox_options.memory_limit:
                # NOTE MLE になる前に firejail -> Python が防ぐのでこれが観測されることは現状ないはずである
                state_result.append(
                    StateCaseResultModel(
                        name="(Entire stage)",
                        status=StatusEnum.ERROR,
                        tags=[
                            EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.UA)
                        ],
                        msg="",
                        err="MLE",
                        system_message=(
                            f"MLE; {resource_usage.ru_maxrss}"
                            f" >= {self._sandbox_options.memory_limit}"
                        ),
                    )
                )

            if not state_result:
                try:
                    _result_stderr, result_json_str = _stderr_remain.rsplit(
                        "\n", maxsplit=1
                    )
                    state_result = [
                        StateCaseResultModel.parse_obj(case_result)
                        for case_result in json.loads(result_json_str)
                    ]
                except Exception:  # pylint:disable=broad-except
                    logger.exception("Error during parse result_json_str")
                    # runnerが責任を果たしていないことになるのでBSE
                    state_result.append(
                        StateCaseResultModel(
                            name="(Entire stage)",
                            status=StatusEnum.FATAL,
                            tags=[
                                EvaluationTagModel.from_dataclass(
                                    BuiltinEvaluationTag.BSE
                                )
                            ],
                            msg="",
                            err="",
                            system_message="Error during parse result_json_str",
                        )
                    )

            logger.debug("state_result = %r", state_result)
            all_case_tags = [
                tag for case_result in state_result for tag in case_result.tags
            ]
            status_set = frozenset(case_result.status for case_result in state_result)
            status_set_sorted = sorted(status_set, key=StatusEnum.to_display_order)
            state_tag_set = sorted(set(all_case_tags))
            state_results[state_name] = StateResultModel(
                runner=StateRunnerModel.parse_state_runner(state.runner),
                cases=[
                    StateCaseResult.from_runner_result(case_result)
                    for case_result in state_result
                ],
                result=ResultModel(
                    status_set=status_set_sorted,
                    time=resource_usage.time_elapse_nsec,
                    memory=resource_usage.ru_maxrss,
                    tag_set=state_tag_set,
                ),
            )
            if any(tag.name in SYSTEM_FAILURE_TAG_NAME_SET for tag in state_tag_set):
                log_subprocess_result(logger, logging.DEBUG, result)
            logger.debug(
                "======== [%s] <terminate> (in %.3f sec, %.3f MiB) ========",
                state_name,
                resource_usage.time_elapse_nsec / 10**9,
                resource_usage.ru_maxrss / 2**10,
            )

            ################################################
            # 次状態の計算
            transition_table: Dict[FrozenSet[StatusEnum], TransitionSpec] = {}
            transition_otherwise: Optional[TransitionSpec] = None
            for transition_rule in self._setting.judge.evaluation.transition_function:
                (
                    (current_state_name, state_outcome),
                    transition_rule_spec,
                ) = transition_rule
                if state_name != current_state_name:
                    continue
                if isinstance(state_outcome, list):
                    state_outcome_status_set = frozenset(
                        StatusEnum(s) for s in state_outcome
                    )
                    transition_table[state_outcome_status_set] = transition_rule_spec
                elif state_outcome == "otherwise":
                    transition_otherwise = transition_rule_spec
            logger.debug("transition_table = %r", transition_table)
            logger.debug("transition_otherwise = %r", transition_otherwise)
            transition_spec: Optional[TransitionSpec] = transition_table.get(
                status_set, transition_otherwise
            )
            logger.debug("transition_spec = %r", transition_spec)
            if transition_spec is None:
                state_tags = [
                    EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.ESE)
                ]
                state_results[state_name] = StateResultModel(
                    runner=StateRunnerModel.parse_state_runner(state.runner),
                    cases=[],
                    result=ResultModel(
                        status_set=[StatusEnum.FATAL],
                        time=None,
                        memory=None,
                        tag_set=state_tags,
                    ),
                )
                break
            next_state_name, overall_grade = transition_spec
            if next_state_name == "$":
                # 終了状態
                break
            # 非終了状態
            state_name = next_state_name

        overall_status_set = frozenset(
            st for sr in state_results.values() for st in sr.result.status_set
        )
        overall_status_set_sorted = sorted(
            overall_status_set, key=StatusEnum.to_display_order
        )

        overall_time = sum(
            filter(None, (sr.result.time for sr in state_results.values()))
        )
        overall_memory = sum(
            filter(None, (sr.result.memory for sr in state_results.values()))
        )
        overall_tag_set = frozenset(
            st for sr in state_results.values() for st in sr.result.tag_set
        )
        overall_tag_set_sorted = sorted(overall_tag_set)

        response = EvaluationResponseV2(
            metadata=EvaluationResponseMetadataModel(
                submission_key="TBD",
                evaluation_key="TBD",
                evaluated_at=datetime.datetime.now(datetime.timezone.utc),
                exercise_concrete=EvaluationResponseMetadataExerciseConcreteModel(
                    name=self._setting.exercise.name,
                    version=self._setting.exercise.version,
                    directory_hash="__placeholder__",
                ),
                evaluator=EvaluationResponseMetadataEvaluatorModel(
                    name="__placeholder__",
                    version="__placeholder__",
                ),
            ),
            state_history=state_history,
            state_results=state_results,
            overall_result=OverallResult(
                status_set=overall_status_set_sorted,
                grade=overall_grade,
                time=overall_time,
                memory=overall_memory,
                tag_set=overall_tag_set_sorted,
            ),
        )
        return response

    _VALID_RUNNER_NAME_SEQ: Final = ("test_runner_py310_unittest.py",)

    def _preprocess(
        self,
        options: EvaluationOptions,
        logger: logging.Logger,
        state_name: CustomStateName,
        state: SettingJudgeEvaluationState,
    ) -> StateEvaluateArgsModel:
        ################################################
        # ランナーの設定検証
        runner_name = state.runner.name
        if runner_name == "test_runner_py37_unittest_v3.py":
            runner_name = "test_runner_py310_unittest.py"
        assert runner_name in self._VALID_RUNNER_NAME_SEQ, runner_name

        # state_runner_version = state.runner['version']
        state_runner_path = os.path.join(TEST_RUNNER_DIR, runner_name)
        # NOTE ここは一般にはファイルに限らないし、pythonスクリプトとも限らないが、他に対応できていない
        assert os.path.isfile(state_runner_path), (
            f"[ERROR] (in {state_name}) runner `{runner_name}` not found"
            f" (expected `{state_runner_path}`)"
        )

        runner_options_json_b64 = encode_parameter(state.runner.options.json())

        ################################################
        # 自動評価の実行場所となるディレクトリの準備
        state_evaluation_dir = os.path.join(options.evaluation_dir, state_name)
        logger.debug("state_evaluation_dir = %r", state_evaluation_dir)
        os.makedirs(state_evaluation_dir, exist_ok=True)
        ################################
        # 評価対象のファイルを複製
        preprocess_rename = self._setting.judge.preprocess.rename
        evaluation_filename = preprocess_rename or options.submission_filename
        try:
            shutil.copyfile(
                os.path.join(options.submission_dir, options.submission_filename),
                os.path.join(state_evaluation_dir, evaluation_filename),
            )
        except FileNotFoundError as exc:
            raise MissConfigurationError(
                f"Submission file not found: {options.submission_filename!r}"
            ) from exc
        ################################
        # 自動評価に必要なファイルを複製
        tester_filename = f"{state_name}.py"
        try:
            shutil.copyfile(
                os.path.join(options.exercise_concrete_dir, tester_filename),
                os.path.join(state_evaluation_dir, tester_filename),
            )
        except FileNotFoundError as exc:
            raise MissConfigurationError(
                f"State script not found: {tester_filename!r}"
            ) from exc
        for required_file in state.required_files:
            assert isinstance(required_file, str)
            dst_filepath = os.path.join(state_evaluation_dir, required_file)
            dst_dir = os.path.dirname(dst_filepath)
            os.makedirs(dst_dir, exist_ok=True)
            try:
                shutil.copyfile(
                    os.path.join(options.exercise_concrete_dir, required_file),
                    dst_filepath,
                )
            except FileNotFoundError as exc:
                raise MissConfigurationError(
                    f"Required file not found: {required_file!r}"
                ) from exc
        ################################
        # 自動評価上の制約の解釈
        try:
            time_limit_second = math.ceil(
                time_limit_to_microseconds(state.time_limit) / 1_000_000
            )
        except AssertionError as exc:
            error_message = f"Invalid time_limit: {state.time_limit!r}"
            raise MissConfigurationError(error_message=error_message) from exc

        return StateEvaluateArgsModel(
            state_runner_path=state_runner_path,
            evaluation_filename=evaluation_filename,
            runner_options_json_b64=runner_options_json_b64,
            time_limit_second=time_limit_second,
        )

    def _evaluate_state(
        self,
        options: EvaluationOptions,
        logger: logging.Logger,
        state_name: CustomStateName,
        state_args: StateEvaluateArgsModel,
    ) -> "subprocess.CompletedProcess[str]":
        ################################################
        # ランナー呼び出し及び結果の解釈
        irregular_tag_set: List[EvaluationTagModel] = []
        result: Optional["subprocess.CompletedProcess[str]"] = None
        try:
            runner_command: Tuple[str, ...] = (
                PYTHON_COMMAND,
                state_args.state_runner_path,
                options.exercise_concrete_dir,
                state_name,
                options.evaluation_dir,
                state_args.evaluation_filename,
                options.evaluation_result_filename + "__" + state_name,
                state_args.runner_options_json_b64,
                "-l",
                options.log_level,
            )

            command = self._environment_options.wrap_command(
                self._sandbox_options.wrap_command(
                    options.exercise_concrete_dir,
                    options.evaluation_dir,
                    self._limitrace_options.wrap_command(
                        runner_command, time_limit=state_args.time_limit_second
                    ),
                )
            )
            logger.debug("command: %s", subprocess.list2cmdline(command))
            # NOTE limitraceでは指定された time_limit に加えて+1秒、killまでには2秒の猶予を与えている。
            relaxed_time_limit_for_subprocess_run = state_args.time_limit_second + 3
            result = subprocess.run(
                command,
                capture_output=True,
                check=False,
                encoding="utf_8",
                timeout=relaxed_time_limit_for_subprocess_run,
            )

        except subprocess.TimeoutExpired as exc:
            # ATTENTION ここを通過するということは、limitraceコマンドの不具合によって
            #           Python側のtimeoutが発動したということであり、実質的にはBSE相当である。
            log_subprocess_result(logger, logging.INFO, exc)
            logger.error(f"Runner timed out with {state_args.time_limit_second=}")
            irregular_tag_set.append(
                EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.TLE)
            )

        except Exception:  # pylint: disable=broad-except
            logger.exception("Unexpected exception")
            irregular_tag_set.append(
                EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.BSE)
            )

        else:
            if result.returncode != 0:
                log_subprocess_result(logger, logging.INFO, result)

                # NOTE firejail には "--deterministic-exit-code" オプションを与え、ステータスコードを保っている。
                # cf. <https://docs.python.org/ja/3/library/subprocess.html#subprocess.CalledProcessError>
                #     > もしプロセスがシグナルによって終了したなら、これは負のシグナル番号になります。
                if (
                    result.returncode == -signal.Signals.SIGKILL.value
                ):  # pylint: disable=no-member
                    # killed by SIGKILL, this can be by SIGTERM-handled submission or OOM killer
                    irregular_tag_set.append(
                        EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.BSE)
                    )
                elif (
                    # firejail による中断 通常TLEが期待されると思われるが状況によりそう
                    # NOTE 呼び出し元で解釈される
                    result.returncode == FIREJAIL_FAILURE_CODE
                    # NOTE 呼び出し元で解釈される
                    or result.returncode == LimitraceOptions.EXIT_TIMED_OUT
                ):
                    pass
                elif result.returncode >= STATUS_CODE_OFFSET:
                    irregular_tag_set.append(
                        EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.ESE)
                    )
                    logger.error(
                        f"Error on test_runner, result.returncode was {result.returncode}"
                    )
                else:
                    irregular_tag_set.append(
                        EvaluationTagModel.from_dataclass(BuiltinEvaluationTag.UA)
                    )
            else:
                log_subprocess_result(logger, logging.DEBUG, result)

        if irregular_tag_set:
            if result is not None:
                state_evaluation_tags = [it.name for it in irregular_tag_set]
                logger.debug(
                    "******** [%s] <%s> *******", state_name, state_evaluation_tags
                )
                logger.debug("%s%s", result.stderr, "[EOF]\n")
                logger.debug("======== [%s] <terminate> ========", state_name)
            raise EvaluationFailureException(irregular_tag_set)

        assert result is not None, result
        return result
