import dataclasses
from typing import TYPE_CHECKING, Dict, Tuple

if TYPE_CHECKING:
    import subprocess


@dataclasses.dataclass
class LimitraceResourceStatistics:
    ru_utime_usec: int
    ru_stime_usec: int
    ru_time_usec: int

    ru_maxrss: int
    ru_minflt: int
    ru_majflt: int
    ru_inblock: int
    ru_oublock: int
    ru_nvcsw: int
    ru_nivcsw: int
    time_elapse_nsec: int


@dataclasses.dataclass
class LimitraceLimitDetection:
    cpu_overuse: int
    memory_overuse: int
    utime_overuse: int
    stime_overuse: int
    as_overuse: int
    rss_overuse: int
    exit_status: int


def _parse_ltsv_line(ltsv_line: str) -> Dict[str, int]:
    return {
        key: int(value)
        for key, value in (p.split(":", 1) for p in ltsv_line.split("\t"))
    }


def get_limitrace_resource_statistics_from_ltsv_line(
    ltsv_line: str,
) -> LimitraceResourceStatistics:
    return LimitraceResourceStatistics(**_parse_ltsv_line(ltsv_line))


def get_limitrace_limit_detection_from_ltsv_line(
    ltsv_line: str,
) -> LimitraceLimitDetection:
    return LimitraceLimitDetection(**_parse_ltsv_line(ltsv_line))


def get_limitrace_resource_statistics_from_completed_process(
    completed_process: "subprocess.CompletedProcess[str]",
) -> LimitraceResourceStatistics:
    rsplitted = completed_process.stderr.rstrip().rsplit("\n", 1)
    assert len(rsplitted) == 2
    ltsv_line = rsplitted[-1]

    return get_limitrace_resource_statistics_from_ltsv_line(ltsv_line)


def get_stderr_result_json_limitrace_resource_statistics(
    completed_process: "subprocess.CompletedProcess[str]",
) -> Tuple[str, LimitraceResourceStatistics, LimitraceLimitDetection]:
    """Example:
    ====    limitrace statistics    ====
    ru_utime_usec:97942     ru_stime_usec:15906     ru_time_usec:113848     ru_maxrss:17476 ru_minflt:6432  ru_majflt:0     ru_inblock:0    ru_oublock:32   ru_nvcsw:6      ru_nivcsw:11    time_elapse_nsec:113447869
    cpu_overuse:0   memory_overuse:0        utime_overuse:0 stime_overuse:0 as_overuse:0    rss_overuse:0   exit_status:0
    """

    try:
        rsplitted = completed_process.stderr.rstrip().rsplit("\n", 3)
        assert len(rsplitted) == 4
        previous, _header_line, rusage_line, detection_line = rsplitted

        return (
            previous,
            get_limitrace_resource_statistics_from_ltsv_line(rusage_line),
            get_limitrace_limit_detection_from_ltsv_line(detection_line),
        )
    except Exception as exc:  # pylint: disable=broad-except
        raise ValueError("Invalid limitrace output format.") from exc
