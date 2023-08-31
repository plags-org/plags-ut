import dataclasses
import logging
import os
import re
import subprocess
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Tuple,
    TypedDict,
    Union,
)

from typing_extensions import TypeAlias

from judge_core.exercise_concrete.common.schema_type import (
    String64,
    String1024,
    StringAscii256,
)

from .const import (
    ENVIRONMENT_ROOT,
    FIREJAIL_COMMAND,
    LIMITRACE_COMMAND,
    TEST_RUNNER_DIR,
)


@dataclasses.dataclass
class EvaluationOptions:
    exercise_concrete_dir: str
    submission_dir: str
    submission_filename: str
    evaluation_dir: str
    evaluation_result_filename: str
    log_level: str = "ERROR"
    dry_run: bool = False


class EnvironmentOptions:
    def __init__(
        self, environment_root_dir: str, environment_name: str, environment_version: str
    ):
        self.environment_root_dir = environment_root_dir
        self.environment_name = environment_name
        self.environment_version = environment_version

    def wrap_command(self, command: Tuple[str, ...]) -> Tuple[str, ...]:
        joined_command = subprocess.list2cmdline(
            (
                "source",
                os.path.join(
                    self.environment_root_dir,
                    self.environment_name,
                    "venv/bin/activate",
                ),
                "&&",
            )
            + command
        )
        return (
            "bash",
            "-c",
            joined_command,
        )


class LimitraceOptions:
    def __init__(
        self,
        # 適当な決め これは保険なので大きくて良い
        time_limit_default: int = 60,
    ) -> None:
        self.time_limit_default = time_limit_default

    def wrap_command(
        self, command: Tuple[str, ...], *, time_limit: Optional[int] = None
    ) -> Tuple[str, ...]:
        time_limit = time_limit or self.time_limit_default
        return (
            LIMITRACE_COMMAND,
            "--signal=TERM",
            f"--kill-after={time_limit + 1}",
            f"{time_limit}",
        ) + command

    EXIT_TIMED_OUT: ClassVar[int] = 124


def _memory_limit_to_bytes(memory_limit: Union[int, str]) -> int:
    """Byte単位に統一する"""
    if isinstance(memory_limit, int):
        return memory_limit
    assert isinstance(memory_limit, str), f"Invalid type: {memory_limit=}"
    valid_postfixes: Dict[str, Callable[[int], int]] = {
        "GiB": lambda x: x * 2**30,
        "MiB": lambda x: x * 2**20,
        "KiB": lambda x: x * 2**10,
        "GB": lambda x: x * 1_000_000_000,
        "MB": lambda x: x * 1_000_000,
        "KB": lambda x: x * 1_000,
        "": lambda x: x,
    }
    match = re.fullmatch(r"([0-9]+)(\w+)", memory_limit, flags=re.ASCII)
    assert match, f"Invalid format: {memory_limit=}"
    limit_number, limit_postfix = match[1], match[2]
    assert limit_postfix in valid_postfixes, f"Invalid postfix: {limit_postfix=}"
    return valid_postfixes[limit_postfix](int(limit_number))


def time_limit_to_microseconds(time_limit: Union[int, str]) -> int:
    """マイクロ秒単位に統一する"""
    if isinstance(time_limit, int):
        return time_limit * 1_000_000
    assert isinstance(time_limit, str), f"Invalid type: {time_limit=}"
    valid_postfixes: Dict[str, Callable[[int], int]] = {
        "m": lambda x: x * 60 * 1_000_000,
        "ms": lambda x: x * 1_000,
        "us": lambda x: x,
        "s": lambda x: x * 1_000_000,
        "": lambda x: x * 1_000_000,
    }
    match = re.fullmatch(r"([0-9]+)(\w*)", time_limit, flags=re.ASCII)
    assert match, f"Invalid format: {time_limit=}"
    limit_number, limit_postfix = match[1], match[2]
    assert limit_postfix in valid_postfixes, f"Invalid postfix: {limit_postfix=}"
    return valid_postfixes[limit_postfix](int(limit_number))


class FirejailOptions:
    def __init__(self, options: dict) -> None:
        self.cpu_limit: int = options.get("cpu_limit", 1)
        self.memory_limit: int = _memory_limit_to_bytes(
            options.get("memory_limit", "256MiB")
        )
        self.network_limit: str = options.get("network_limit", 0)

    def wrap_command(
        self, exercise_concrete_dir: str, evaluation_dir: str, command: Tuple[str, ...]
    ) -> Tuple[str, ...]:
        # HOMEに評価用ディレクトリを展開し、その他は封じたかったが開発環境側との兼ね合いで一旦凍結
        paths_to_be_shared = (
            ENVIRONMENT_ROOT,
            LIMITRACE_COMMAND,
            TEST_RUNNER_DIR,
            exercise_concrete_dir,
            evaluation_dir,
        )
        # このあたりでは配下の一部ディレクトリを指定したかったが無理だった NOTE PR案件かもしれない
        # home_allow_paths = ','.join(path for path in paths_to_be_shared if path.startswith('/home')) or '_' # noqa:E501
        # opt_allow_paths = ','.join(path for path in paths_to_be_shared if path.startswith('/opt')) or '_' # noqa:E501
        has_home_allow_paths = any(
            path.startswith("/home") for path in paths_to_be_shared
        )
        has_opt_allow_paths = any(
            path.startswith("/opt") for path in paths_to_be_shared
        )
        # NOTE firejail sandbox のデバッグ時にのみ利用する
        # ATTENTION 本番にTrueでリリースしてはいけない
        for_debug = False
        return (
            (
                "cd",
                "/srv",
                "&&",
                FIREJAIL_COMMAND,
            )
            + (("--allow-debuggers",) * for_debug)
            + ("--seccomp=mbind",)
            + (
                (f'--cpu={",".join(map(str, range(self.cpu_limit)))}',)
                if self.cpu_limit
                else ()
            )
            + ((f"--rlimit-as={self.memory_limit}",) if self.memory_limit else ())
            # ) + ('--rlimit-cpu=60',   # NOTE ひとまず Python subprocess.run で保険をかけている
            + ("--hostname=plags_judge",)
            + ("--net=none",)
            + ("--caps.drop=all",)
            # NOTE 残念ながらパラメータ必須なものもある PR投げたい
            #      "If no listed file is found, /opt directory will be empty." なので _ でとりあえず埋める
            # NOTE /var を封じられないのは少し気がかりだが一旦忘れる
            + ("--private-bin=bash",)
            + ("--private-dev",)
            + ("--private-etc=_",)
            # + ("--private-lib=_",)
            + (("--private",) if not has_home_allow_paths else ())  # かわりに private を使う
            + (("--private-opt=_",) if not has_opt_allow_paths else ())
            + ("--private-srv=_",)
            + ("--private-tmp",)
            # 読み取り専用を注釈
            + tuple(
                f"--read-only={path}"
                for path in (
                    "/opt",
                    "/home",
                )
            )
            # 評価用ディレクトリにのみ書き込み権限を付与
            + (f"--read-write={evaluation_dir}",)
            # # WORKAROUND ついでに書き込み権限を与えてみておく
            # + (f'--read-write={ENVIRONMENT_ROOT}',)
            + (("--private-bin=bash,strace",) * for_debug)
            + ("--deterministic-exit-code",)
            + ("-c",)
            + command
        )
        # Try following options in some time:
        # --output=logfile
        # --output-stderr=logfile


class MissConfigurationError(Exception):
    """設定不備によるエラー"""

    def __init__(self, error_message: str, *args: Any) -> None:
        self.error_message = error_message
        super().__init__(*args)


LogLevel: TypeAlias = int


def log_subprocess_result(
    logger: logging.Logger,
    log_level: LogLevel,
    result: Union[
        "subprocess.CompletedProcess[str]",
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ],
) -> None:
    returncode: Optional[int] = None
    if isinstance(result, (subprocess.CompletedProcess, subprocess.CalledProcessError)):
        returncode = result.returncode
    logger.log(
        log_level,
        "============ [%s] ==== <returncode=%r> ====\n"
        "%s\n"
        "============ <^ stdout ^> ============\n"
        "%s\n"
        "============ <^ stderr ^> ============",
        __file__,
        returncode,
        result.stdout,
        result.stderr,
    )


_EnvironmentName: TypeAlias = str


def get_environment_list() -> List[_EnvironmentName]:
    return [
        env_name
        for env_name in os.listdir(ENVIRONMENT_ROOT)
        if all(
            (
                env_name[0] not in "._-",  # .pyenv などを除外
                os.path.isdir(os.path.join(ENVIRONMENT_ROOT, env_name)),
                os.path.isfile(
                    os.path.join(ENVIRONMENT_ROOT, env_name, "environment_ready")
                ),
            )
        )
    ]


# TypeAlias
ResultType = str
EvaluationTag = str


class Result(TypedDict):
    result_types: List[ResultType]
    grade: Optional[int]
    time: Optional[int]
    memory: Optional[int]
    status_set: List[EvaluationTag]
    evaluation_tags: List[EvaluationTag]


class AggregatedResult(TypedDict):
    is_accepted: bool
    grade: Optional[int]
    time: Optional[int]
    memory: Optional[int]
    status_set: List[EvaluationTag]
    evaluation_tags: List[EvaluationTag]


class StateRunner(TypedDict):
    name: str
    version: str


class StateCaseResult(TypedDict):
    name: String64
    result_type: ResultType
    grade: Optional[int]
    status_set: List[EvaluationTag]
    evaluation_tags: List[EvaluationTag]
    input: String1024
    output: String1024
    message: String1024
    debug_message: String1024


class StateResult(TypedDict):
    runner: StateRunner
    cases: List[StateCaseResult]
    result: Result


class EvaluationResponseMetadataExerciseConcrete(TypedDict):
    name: String64
    version: String64
    directory_hash: String64


class EvaluationResponseMetadataEvaluator(TypedDict):
    name: String64
    version: String64


class EvaluationResponseMetadata(TypedDict):
    submission_key: StringAscii256
    evaluation_key: StringAscii256
    evaluated_at_iso8601: str  # YYYY-MM-DD hh:mm:ss+09:00 など ISO8601
    exercise_concrete: EvaluationResponseMetadataExerciseConcrete

    evaluator: EvaluationResponseMetadataEvaluator
