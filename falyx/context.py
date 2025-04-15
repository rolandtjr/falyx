"""context.py"""
import time
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExecutionContext(BaseModel):
    name: str
    args: tuple = ()
    kwargs: dict = {}
    action: Any
    result: Any | None = None
    exception: Exception | None = None
    start_time: float | None = None
    end_time: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def start_timer(self):
        self.start_time = time.perf_counter()

    def stop_timer(self):
        self.end_time = time.perf_counter()

    @property
    def duration(self) -> Optional[float]:
        if self.start_time is not None and self.end_time is not None:
            return self.end_time - self.start_time
        return None

    @property
    def success(self) -> bool:
        return self.exception is None

    @property
    def status(self) -> str:
        return "OK" if self.success else "ERROR"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "result": self.result,
            "exception": repr(self.exception) if self.exception else None,
            "duration": self.duration,
            "extra": self.extra,
        }

    def log_summary(self, logger=None):
        summary = self.as_dict()
        msg = f"[SUMMARY] {summary['name']} | "

        if self.start_time:
            start_str = datetime.fromtimestamp(self.start_time).strftime("%H:%M:%S")
            msg += f"Start: {start_str} | "

        if self.end_time:
            end_str = datetime.fromtimestamp(self.end_time).strftime("%H:%M:%S")
            msg += f"End: {end_str} | "

        msg += f"Duration: {summary['duration']:.3f}s | "

        if summary["exception"]:
            msg += f"❌ Exception: {summary['exception']}"
        else:
            msg += f"✅ Result: {summary['result']}"
        (logger or print)(msg)

    def to_log_line(self) -> str:
        """Structured flat-line format for logging and metrics."""
        duration_str = f"{self.duration:.3f}s" if self.duration is not None else "n/a"
        exception_str = f"{type(self.exception).__name__}: {self.exception}" if self.exception else "None"
        return (
            f"[{self.name}] status={self.status} duration={duration_str} "
            f"result={repr(self.result)} exception={exception_str}"
        )

    def __str__(self) -> str:
        duration_str = f"{self.duration:.3f}s" if self.duration is not None else "n/a"
        result_str = f"Result: {repr(self.result)}" if self.success else f"Exception: {self.exception}"
        return (
            f"<ExecutionContext '{self.name}' | {self.status} | "
            f"Duration: {duration_str} | {result_str}>"
        )

    def __repr__(self) -> str:
        return (
            f"ExecutionContext("
            f"name={self.name!r}, "
            f"duration={f'{self.duration:.3f}' if self.duration is not None else 'n/a'}, "
            f"result={self.result!r}, "
            f"exception={self.exception!r})"
        )


class ResultsContext(BaseModel):
    name: str
    results: list[Any] = Field(default_factory=list)
    errors: list[tuple[int, Exception]] = Field(default_factory=list)
    current_index: int = -1
    is_parallel: bool = False
    shared_result: Any | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def add_result(self, result: Any) -> None:
        self.results.append(result)

    def set_shared_result(self, result: Any) -> None:
        self.shared_result = result
        if self.is_parallel:
            self.results.append(result)

    def last_result(self) -> Any:
        if self.is_parallel:
            return self.shared_result
        return self.results[-1] if self.results else None

    def __str__(self) -> str:
        parallel_label = "Parallel" if self.is_parallel else "Sequential"
        return (
            f"<{parallel_label}ResultsContext '{self.name}' | "
            f"Results: {self.results} | "
            f"Errors: {self.errors}>"
        )
