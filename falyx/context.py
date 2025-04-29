# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""context.py"""
import time
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console


class ExecutionContext(BaseModel):
    name: str
    args: tuple = ()
    kwargs: dict = {}
    action: Any
    result: Any | None = None
    exception: Exception | None = None

    start_time: float | None = None
    end_time: float | None = None
    start_wall: datetime | None = None
    end_wall: datetime | None = None

    extra: dict[str, Any] = Field(default_factory=dict)
    console: Console = Field(default_factory=lambda: Console(color_system="auto"))

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def start_timer(self):
        self.start_wall = datetime.now()
        self.start_time = time.perf_counter()

    def stop_timer(self):
        self.end_time = time.perf_counter()
        self.end_wall = datetime.now()

    @property
    def duration(self) -> float | None:
        if self.start_time is None:
            return None
        if self.end_time is None:
            return time.perf_counter() - self.start_time
        return self.end_time - self.start_time

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
        message = [f"[SUMMARY] {summary['name']} | "]

        if self.start_wall:
            message.append(f"Start: {self.start_wall.strftime('%H:%M:%S')} | ")

        if self.end_time:
            message.append(f"End: {self.end_wall.strftime('%H:%M:%S')} | ")

        message.append(f"Duration: {summary['duration']:.3f}s | ")

        if summary["exception"]:
            message.append(f"❌ Exception: {summary['exception']}")
        else:
            message.append(f"✅ Result: {summary['result']}")
        (logger or self.console.print)("".join(message))

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

if __name__ == "__main__":
    import asyncio

    async def demo():
        ctx = ExecutionContext(name="test", action="demo")
        ctx.start_timer()
        await asyncio.sleep(0.2)
        ctx.stop_timer()
        ctx.result = "done"
        ctx.log_summary()

    asyncio.run(demo())
