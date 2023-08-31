import cProfile
import datetime
import pstats
import time
from types import TracebackType
from typing import IO, Optional, Type


class ProfileContext:
    def __init__(self, profile_output_path: Optional[str] = None) -> None:
        self.profile_output_filepath = profile_output_path
        self.profile = cProfile.Profile()
        self.elapsed_ns: Optional[int] = None
        self.time_started_ns: int = 0
        self.time_finished_ns: int = 0
        self.datetime_started: Optional[datetime.datetime] = None
        self.datetime_finished: Optional[datetime.datetime] = None

    def __enter__(self) -> "ProfileContext":
        self.datetime_started = datetime.datetime.now()
        self.time_started_ns = time.monotonic_ns()

        self.profile.enable()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: TracebackType,
    ) -> None:
        self.profile.disable()

        self.time_finished_ns = time.monotonic_ns()
        self.datetime_finished = datetime.datetime.now()

        self.elapsed_ns = self.time_finished_ns - self.time_started_ns

        if self.profile_output_filepath:
            self.dump_profile(self.profile_output_filepath)

    def get_elapsed_ns(self) -> int:
        assert self.elapsed_ns is not None
        return self.elapsed_ns

    def get_elapsed_seconds(self) -> float:
        assert self.elapsed_ns is not None
        return self.elapsed_ns / 1_000_000_000

    def write_cumulative_stats(self, stream: IO, *, limit: int = 256) -> None:
        ps = pstats.Stats(self.profile, stream=stream)
        ps.sort_stats("cumulative").print_stats(limit)

    def dump_profile(self, profile_output_filepath: str, *, limit: int = 256) -> None:
        self.profile.dump_stats(profile_output_filepath)
        with open(profile_output_filepath + ".txt", "w") as f:
            self.write_cumulative_stats(f, limit=limit)
