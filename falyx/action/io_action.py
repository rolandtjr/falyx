# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""io_action.py
BaseIOAction: A base class for stream- or buffer-based IO-driven Actions.

This module defines `BaseIOAction`, a specialized variant of `BaseAction`
that interacts with standard input and output, enabling command-line pipelines,
text filters, and stream processing tasks.

Features:
- Supports buffered or streaming input modes.
- Reads from stdin and writes to stdout automatically.
- Integrates with lifecycle hooks and retry logic.
- Subclasses must implement `from_input()`, `to_output()`, and `_run()`.

Common usage includes shell-like filters, input transformers, or any tool that
needs to consume input from another process or pipeline.
"""
import asyncio
import shlex
import subprocess
import sys
from typing import Any, Callable

from rich.tree import Tree

from falyx.action.base import BaseAction
from falyx.context import ExecutionContext
from falyx.exceptions import FalyxError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.logger import logger
from falyx.themes import OneColors


class BaseIOAction(BaseAction):
    """
    Base class for IO-driven Actions that operate on stdin/stdout input streams.

    Designed for use in shell pipelines or programmatic workflows that pass data
    through chained commands. It handles reading input, transforming it, and
    emitting output — either as a one-time buffered operation or line-by-line streaming.

    Core responsibilities:
    - Reads input from stdin or previous action result.
    - Supports buffered or streaming modes via `mode`.
    - Parses input via `from_input()` and formats output via `to_output()`.
    - Executes `_run()` with the parsed input.
    - Writes output to stdout.

    Subclasses must implement:
    - `from_input(raw)`: Convert raw stdin or injected data into typed input.
    - `to_output(data)`: Convert result into output string or bytes.
    - `_run(parsed_input, *args, **kwargs)`: Core execution logic.

    Attributes:
        mode (str): Either "buffered" or "stream". Controls input behavior.
        inject_last_result (bool): Whether to inject shared context input.
    """

    def __init__(
        self,
        name: str,
        *,
        hooks: HookManager | None = None,
        mode: str = "buffered",
        logging_hooks: bool = True,
        inject_last_result: bool = True,
    ):
        super().__init__(
            name=name,
            hooks=hooks,
            logging_hooks=logging_hooks,
            inject_last_result=inject_last_result,
        )
        self.mode = mode

    def from_input(self, raw: str | bytes) -> Any:
        raise NotImplementedError

    def to_output(self, result: Any) -> str | bytes:
        raise NotImplementedError

    async def _resolve_input(
        self, args: tuple[Any], kwargs: dict[str, Any]
    ) -> str | bytes:
        data = await self._read_stdin()
        if data:
            return self.from_input(data)

        if len(args) == 1:
            return self.from_input(args[0])

        if self.inject_last_result and self.shared_context:
            return self.shared_context.last_result()

        logger.debug(
            "[%s] No input provided and no last result found for injection.", self.name
        )
        raise FalyxError("No input provided and no last result to inject.")

    def get_infer_target(self) -> tuple[Callable[..., Any] | None, dict[str, Any] | None]:
        return None, None

    async def __call__(self, *args, **kwargs):
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=kwargs,
            action=self,
        )

        context.start_timer()
        await self.hooks.trigger(HookType.BEFORE, context)

        try:
            if self.mode == "stream":
                line_gen = await self._read_stdin_stream()
                async for _ in self._stream_lines(line_gen, args, kwargs):
                    pass
                result = getattr(self, "_last_result", None)
            else:
                parsed_input = await self._resolve_input(args, kwargs)
                result = await self._run(parsed_input)
                output = self.to_output(result)
                await self._write_stdout(output)
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return result
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def _read_stdin(self) -> str:
        if not sys.stdin.isatty():
            return await asyncio.to_thread(sys.stdin.read)
        return ""

    async def _read_stdin_stream(self) -> Any:
        """Returns a generator that yields lines from stdin in a background thread."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: iter(sys.stdin))

    async def _stream_lines(self, line_gen, args, kwargs):
        for line in line_gen:
            parsed = self.from_input(line)
            result = await self._run(parsed, *args, **kwargs)
            self._last_result = result
            output = self.to_output(result)
            await self._write_stdout(output)
            yield result

    async def _write_stdout(self, data: str) -> None:
        await asyncio.to_thread(sys.stdout.write, data)
        await asyncio.to_thread(sys.stdout.flush)

    async def _run(self, parsed_input: Any, *args, **kwargs) -> Any:
        """Subclasses should override this with actual logic."""
        raise NotImplementedError("Must implement _run()")

    def __str__(self):
        return f"<{self.__class__.__name__} '{self.name}' IOAction>"

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.GREEN_b}]⚙ IOAction[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_into}')[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))


class ShellAction(BaseIOAction):
    """
    ShellAction wraps a shell command template for CLI pipelines.

    This Action takes parsed input (from stdin, literal, or last_result),
    substitutes it into the provided shell command template, and executes
    the command asynchronously using subprocess.

    Designed for quick integration with shell tools like `grep`, `ping`, `jq`, etc.

    ⚠️ Security Warning:
    By default, ShellAction uses `shell=True`, which can be dangerous with
    unsanitized input. To mitigate this, set `safe_mode=True` to use `shell=False`
    with `shlex.split()`.

    Features:
    - Automatically handles input parsing (str/bytes)
    - `safe_mode=True` disables shell interpretation and runs with `shell=False`
    - Captures stdout and stderr from shell execution
    - Raises on non-zero exit codes with stderr as the error
    - Result is returned as trimmed stdout string

    Args:
        name (str): Name of the action.
        command_template (str): Shell command to execute. Must include `{}` to include
                                input. If no placeholder is present, the input is not
                                included.
        safe_mode (bool): If True, runs with `shell=False` using shlex parsing
                          (default: False).
    """

    def __init__(
        self, name: str, command_template: str, safe_mode: bool = False, **kwargs
    ):
        super().__init__(name=name, **kwargs)
        self.command_template = command_template
        self.safe_mode = safe_mode

    def from_input(self, raw: str | bytes) -> str:
        if not isinstance(raw, (str, bytes)):
            raise TypeError(
                f"{self.name} expected str or bytes input, got {type(raw).__name__}"
            )
        return raw.strip() if isinstance(raw, str) else raw.decode("utf-8").strip()

    def get_infer_target(self) -> tuple[Callable[..., Any] | None, dict[str, Any] | None]:
        if sys.stdin.isatty():
            return self._run, {"parsed_input": {"help": self.command_template}}
        return None, None

    async def _run(self, parsed_input: str) -> str:
        # Replace placeholder in template, or use raw input as full command
        command = self.command_template.format(parsed_input)
        if self.safe_mode:
            try:
                args = shlex.split(command)
            except ValueError as error:
                raise FalyxError(f"Invalid command template: {error}")
            result = subprocess.run(args, capture_output=True, text=True, check=True)
        else:
            result = subprocess.run(
                command, shell=True, text=True, capture_output=True, check=True
            )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def to_output(self, result: str) -> str:
        return result

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.GREEN_b}]⚙ ShellAction[/] '{self.name}'"]
        label.append(f"\n[dim]Template:[/] {self.command_template}")
        label.append(
            f"\n[dim]Safe mode:[/] {'Enabled' if self.safe_mode else 'Disabled'}"
        )
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_into}')[/dim]")
        tree = parent.add("".join(label)) if parent else Tree("".join(label))
        if not parent:
            self.console.print(tree)

    def __str__(self):
        return (
            f"ShellAction(name={self.name!r}, command_template={self.command_template!r},"
            f" safe_mode={self.safe_mode})"
        )
