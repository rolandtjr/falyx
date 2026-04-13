# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Context models for Falyx execution and invocation state.

This module defines the core context objects used throughout Falyx to track both
runtime execution metadata and routed invocation-path state.

It provides:
    - `ExecutionContext` for per-action execution details such as arguments,
      results, exceptions, timing, and summary logging.
    - `SharedContext` for transient shared state across grouped or chained
      actions, including propagated results, indexed errors, and arbitrary
      shared data.
    - `InvocationSegment` for representing a single styled token within a
      rendered invocation path.
    - `InvocationContext` for capturing the current routed command path as an
      immutable value object that supports both plain-text and Rich-markup
      rendering.

Together, these models support Falyx lifecycle hooks, execution tracing,
history/introspection, and context-aware help and usage rendering across CLI
and menu modes.
"""
from __future__ import annotations

import time
from datetime import datetime
from traceback import format_exception
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from rich.console import Console
from rich.markup import escape

from falyx.console import console
from falyx.mode import FalyxMode


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
        exception (BaseException | None): The exception raised, if execution failed.
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
    traceback: str | None = None
    _exception: BaseException | None = None

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
    def exception(self) -> BaseException | None:
        return self._exception

    @exception.setter
    def exception(self, exc: BaseException | None):
        self._exception = exc
        if exc is not None:
            self.traceback = "".join(format_exception(exc)).strip()

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
            "traceback": self.traceback,
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
        errors (list[tuple[int, BaseException]]): Indexed list of errors from failed actions.
        current_index (int): Index of the currently executing action (used in chains).
        is_concurrent (bool): Whether the context is used in concurrent mode (ActionGroup).
        shared_result (Any | None): Optional shared value available to all actions in
                                    concurrent mode.
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
    errors: list[tuple[int, BaseException]] = Field(default_factory=list)
    current_index: int = -1
    is_concurrent: bool = False
    shared_result: Any | None = None

    share: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def add_result(self, result: Any) -> None:
        self.results.append(result)

    def add_error(self, index: int, error: BaseException) -> None:
        self.errors.append((index, error))

    def set_shared_result(self, result: Any) -> None:
        self.shared_result = result
        if self.is_concurrent:
            self.results.append(result)

    def last_result(self) -> Any:
        if self.is_concurrent:
            return self.shared_result
        return self.results[-1] if self.results else None

    def get(self, key: str, default: Any = None) -> Any:
        return self.share.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.share[key] = value

    def __str__(self) -> str:
        concurrent_label = "Concurrent" if self.is_concurrent else "Sequential"
        return (
            f"<{concurrent_label}SharedContext '{self.name}' | "
            f"Results: {self.results} | "
            f"Errors: {self.errors}>"
        )


class InvocationSegment(BaseModel):
    """Styled path segment used to build an invocation display path.

    `InvocationSegment` represents a single token within an `InvocationContext`,
    such as a namespace key, command key, or alias. It stores the raw display
    text and an optional Rich style so invocation paths can be rendered either
    as plain text or styled markup.

    Attributes:
        text (str): Display text for this path segment.
        style (str | None): Optional Rich style applied when rendering this
            segment in markup output.
    """

    text: str
    style: str | None = None


class InvocationContext(BaseModel):
    """Immutable invocation-path context for routed Falyx help and execution.

    `InvocationContext` captures the current displayable command path as the router
    descends through namespaces and commands. It stores both the raw typed path
    (`typed_path`) and a styled segment representation (`segments`) so the same
    context can be rendered as plain text or Rich markup.

    This model is intended to be treated as an immutable value object. Methods such
    as `with_path_segment()` and `without_last_path_segment()` return new context
    instances rather than mutating the existing one.

    Attributes:
        program (str): Root program name used in CLI-mode help and usage output.
        program_style (str): Rich style applied to the program name when rendering
            `markup_path`.
        typed_path (list[str]): Raw invocation tokens collected during routing,
            excluding the root program name.
        segments (list[InvocationSegment]): Styled path segments used to render the
            invocation path with Rich markup.
        mode (FalyxMode): Active Falyx mode for this invocation context. This is
            used to determine whether the path should include the program name.
        is_preview (bool): Whether the current invocation is a preview flow rather
            than a normal execution flow.
    """

    program: str = ""
    program_style: str = ""
    typed_path: list[str] = Field(default_factory=list)
    segments: list[InvocationSegment] = Field(default_factory=list)
    mode: FalyxMode = FalyxMode.MENU
    is_preview: bool = False

    @property
    def is_cli_mode(self) -> bool:
        """Whether this context should render using CLI path semantics.

        Returns:
            bool: `True` when the invocation is not in menu mode, meaning rendered
            paths should include the program name. `False` when in menu mode.
        """
        return self.mode != FalyxMode.MENU

    def with_path_segment(
        self,
        token: str,
        *,
        style: str | None = None,
    ) -> InvocationContext:
        """Return a new context with one additional path segment appended.

        This method preserves the current context and creates a new
        `InvocationContext` with the provided token added to both `typed_path` and
        `segments`.

        Args:
            token (str): Raw path token to append, such as a namespace key,
                command key, or alias.
            style (str | None): Optional Rich style for the appended segment.

        Returns:
            InvocationContext: A new context containing the appended path segment.
        """
        return InvocationContext(
            program=self.program,
            program_style=self.program_style,
            typed_path=[*self.typed_path, token],
            segments=[*self.segments, InvocationSegment(text=token, style=style)],
            mode=self.mode,
            is_preview=self.is_preview,
        )

    def without_last_path_segment(self) -> InvocationContext:
        """Return a new context with the last path segment removed.

        This method preserves the current context and creates a new
        `InvocationContext` with the last token removed from both `typed_path` and
        `segments`.

        Returns:
            InvocationContext: A new context with the last path segment removed, or the
            current context if no path segments are present.
        """
        if not self.typed_path:
            return self
        return InvocationContext(
            program=self.program,
            program_style=self.program_style,
            typed_path=self.typed_path[:-1],
            segments=self.segments[:-1],
            mode=self.mode,
            is_preview=self.is_preview,
        )

    @property
    def plain_path(self) -> str:
        """Render the invocation path as plain text.

        In CLI mode, the rendered path includes the root program name followed by
        all collected path segments. In menu mode, only the collected path segments
        are rendered.

        Returns:
            str: Plain-text invocation path suitable for logs, comparisons, or
            non-styled help output.
        """
        parts = [seg.text for seg in self.segments]
        if self.is_cli_mode:
            return " ".join([self.program, *parts]).strip()
        return " ".join(parts).strip()

    @property
    def markup_path(self) -> str:
        """Render the invocation path as escaped Rich markup.

        In CLI mode, the root program name is included and styled with
        `program_style` when provided. Each path segment is escaped and styled
        using its associated `InvocationSegment.style` value when present.

        Returns:
            str: Rich-markup invocation path suitable for help and usage rendering.
        """
        parts: list[str] = []
        if self.is_cli_mode and self.program:
            if self.program_style:
                parts.append(
                    f"[{self.program_style}]{escape(self.program)}[/{self.program_style}]"
                )
            else:
                parts.append(escape(self.program))

        for seg in self.segments:
            if seg.style:
                parts.append(f"[{seg.style}]{escape(seg.text)}[/{seg.style}]")
            else:
                parts.append(escape(seg.text))
        return " ".join(parts).strip()


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
