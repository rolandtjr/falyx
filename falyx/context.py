# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Execution context management for Falyx CLI actions.

This module defines `ExecutionContext` and `SharedContext`, which are responsible for
capturing per-action and cross-action metadata during CLI workflow execution. These
context objects provide structured introspection, result tracking, error recording,
and time-based performance metrics.

- `ExecutionContext`: Captures runtime information for a single action execution,
  including arguments, results, exceptions, timing, and logging.
- `SharedContext`: Maintains shared state and result propagation across
  `ChainedAction` or `ActionGroup` executions.

These contexts enable rich introspection, traceability, and workflow coordination,
supporting hook lifecycles, retries, and structured output generation.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console

from falyx.console import console


class ExecutionContext(BaseModel):
    """
    Represents the runtime metadata and state for a single action execution.

    The `ExecutionContext` tracks arguments, results, exceptions, timing, and
    additional metadata for each invocation of a Falyx `BaseAction`. It provides
    integration with the Falyx hook system and execution registry, enabling lifecycle
    management, diagnostics, and structured logging.

    Attributes:
        name (str): The name of the action being executed.
        args (tuple): Positional arguments passed to the action.
        kwargs (dict): Keyword arguments passed to the action.
        action (BaseAction | Callable): The action instance being executed.
        result (Any | None): The result of the action, if successful.
        exception (Exception | None): The exception raised, if execution failed.
        start_time (float | None): High-resolution performance start time.
        end_time (float | None): High-resolution performance end time.
        start_wall (datetime | None): Wall-clock timestamp when execution began.
        end_wall (datetime | None): Wall-clock timestamp when execution ended.
        extra (dict): Metadata for custom introspection or special use by Actions.
        console (Console): Rich console instance for logging or UI output.
        shared_context (SharedContext | None): Optional shared context when running in
                                               a chain or group.

    Properties:
        duration (float | None): The execution duration in seconds.
        success (bool): Whether the action completed without raising an exception.
        status (str): Returns "OK" if successful, otherwise "ERROR".

    Methods:
        start_timer(): Starts the timing and timestamp tracking.
        stop_timer(): Stops timing and stores end timestamps.
        log_summary(logger=None): Logs a rich or plain summary of execution.
        to_log_line(): Returns a single-line log entry for metrics or tracing.
        as_dict(): Serializes core result and diagnostic metadata.
        get_shared_context(): Returns the shared context or creates a default one.

    This class is used internally by all Falyx actions and hook events. It ensures
    consistent tracking and reporting across asynchronous workflows, including CLI-driven
    and automated batch executions.
    """

    name: str
    args: tuple = ()
    kwargs: dict = Field(default_factory=dict)
    action: Any
    result: Any | None = None
    exception: Exception | None = None

    start_time: float | None = None
    end_time: float | None = None
    start_wall: datetime | None = None
    end_wall: datetime | None = None

    index: int | None = None

    extra: dict[str, Any] = Field(default_factory=dict)
    console: Console = console

    shared_context: SharedContext | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def start_timer(self):
        self.start_wall = datetime.now()
        self.start_time = time.perf_counter()

    def stop_timer(self):
        self.end_time = time.perf_counter()
        self.end_wall = datetime.now()

    def get_shared_context(self) -> SharedContext:
        if not self.shared_context:
            raise ValueError(
                "SharedContext is not set. This context is not part of a chain or group."
            )
        return self.shared_context

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

    @property
    def signature(self) -> str:
        """
        Returns a string representation of the action signature, including
        its name and arguments.
        """
        args = ", ".join(map(repr, self.args))
        kwargs = ", ".join(f"{key}={value!r}" for key, value in self.kwargs.items())
        signature = ", ".join(filter(None, [args, kwargs]))
        return f"{self.action} ({signature})"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "result": self.result,
            "exception": repr(self.exception) if self.exception else None,
            "duration": self.duration,
            "extra": self.extra,
        }

    def log_summary(self, logger=None) -> None:
        summary = self.as_dict()
        message = [f"[SUMMARY] {summary['name']} | "]

        if self.start_wall:
            message.append(f"Start: {self.start_wall.strftime('%H:%M:%S')} | ")

        if self.end_wall:
            message.append(f"End: {self.end_wall.strftime('%H:%M:%S')} | ")

        message.append(f"Duration: {summary['duration']:.3f}s | ")

        if summary["exception"]:
            message.append(f"Exception: {summary['exception']}")
        else:
            message.append(f"Result: {summary['result']}")
        (logger or self.console.print)("".join(message))

    def to_log_line(self) -> str:
        """Structured flat-line format for logging and metrics."""
        duration_str = f"{self.duration:.3f}s" if self.duration is not None else "n/a"
        exception_str = (
            f"{type(self.exception).__name__}: {self.exception}"
            if self.exception
            else "None"
        )
        return (
            f"[{self.name}] status={self.status} duration={duration_str} "
            f"result={repr(self.result)} exception={exception_str}"
        )

    def __str__(self) -> str:
        duration_str = f"{self.duration:.3f}s" if self.duration is not None else "n/a"
        result_str = (
            f"Result: {repr(self.result)}"
            if self.success
            else f"Exception: {self.exception}"
        )
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


class SharedContext(BaseModel):
    """
    SharedContext maintains transient shared state during the execution
    of a ChainedAction or ActionGroup.

    This context object is passed to all actions within a chain or group,
    enabling result propagation, shared data exchange, and coordinated
    tracking of execution order and failures.

    Attributes:
        name (str): Identifier for the context (usually the parent action name).
        results (list[Any]): Captures results from each action, in order of execution.
        errors (list[tuple[int, Exception]]): Indexed list of errors from failed actions.
        current_index (int): Index of the currently executing action (used in chains).
        is_parallel (bool): Whether the context is used in parallel mode (ActionGroup).
        shared_result (Any | None): Optional shared value available to all actions in
                                    parallel mode.
        share (dict[str, Any]): Custom shared key-value store for user-defined
                                communication
            between actions (e.g., flags, intermediate data, settings).

    Note:
        SharedContext is only used within grouped or chained workflows. It should not be
        used for standalone `Action` executions, where state should be scoped to the
        individual ExecutionContext instead.

    Example usage:
        - In a ChainedAction: last_result is pulled from `results[-1]`.
        - In an ActionGroup: all actions can read/write `shared_result` or use `share`.

    This class supports fault-tolerant and modular composition of CLI workflows
    by enabling flexible intra-action communication without global state.
    """

    name: str
    action: Any
    results: list[Any] = Field(default_factory=list)
    errors: list[tuple[int, Exception]] = Field(default_factory=list)
    current_index: int = -1
    is_parallel: bool = False
    shared_result: Any | None = None

    share: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def add_result(self, result: Any) -> None:
        self.results.append(result)

    def add_error(self, index: int, error: Exception) -> None:
        self.errors.append((index, error))

    def set_shared_result(self, result: Any) -> None:
        self.shared_result = result
        if self.is_parallel:
            self.results.append(result)

    def last_result(self) -> Any:
        if self.is_parallel:
            return self.shared_result
        return self.results[-1] if self.results else None

    def get(self, key: str, default: Any = None) -> Any:
        return self.share.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.share[key] = value

    def __str__(self) -> str:
        parallel_label = "Parallel" if self.is_parallel else "Sequential"
        return (
            f"<{parallel_label}SharedContext '{self.name}' | "
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
