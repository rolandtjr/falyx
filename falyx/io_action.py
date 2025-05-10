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
import subprocess
import sys
from typing import Any

from rich.tree import Tree

from falyx.action import BaseAction
from falyx.context import ExecutionContext
from falyx.exceptions import FalyxError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.themes.colors import OneColors
from falyx.utils import logger


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
        self._requires_injection = True

    def from_input(self, raw: str | bytes) -> Any:
        raise NotImplementedError

    def to_output(self, data: Any) -> str | bytes:
        raise NotImplementedError

    async def _resolve_input(self, kwargs: dict[str, Any]) -> str | bytes:
        last_result = kwargs.pop(self.inject_into, None)

        data = await self._read_stdin()
        if data:
            return self.from_input(data)

        if last_result is not None:
            return last_result

        if self.inject_last_result and self.shared_context:
            return self.shared_context.last_result()

        logger.debug(
            "[%s] No input provided and no last result found for injection.", self.name
        )
        raise FalyxError("No input provided and no last result to inject.")

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
                async for line in self._stream_lines(line_gen, args, kwargs):
                    pass
                result = getattr(self, "_last_result", None)
            else:
                parsed_input = await self._resolve_input(kwargs)
                result = await self._run(parsed_input, *args, **kwargs)
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

    ⚠️ Warning:
    Be cautious when using ShellAction with untrusted user input. Since it uses
    `shell=True`, unsanitized input can lead to command injection vulnerabilities.
    Avoid passing raw user input directly unless the template or use case is secure.

    Features:
    - Automatically handles input parsing (str/bytes)
    - Captures stdout and stderr from shell execution
    - Raises on non-zero exit codes with stderr as the error
    - Result is returned as trimmed stdout string
    - Compatible with ChainedAction and Command.requires_input detection

    Args:
        name (str): Name of the action.
        command_template (str): Shell command to execute. Must include `{}` to include input.
                                If no placeholder is present, the input is not included.
    """

    def __init__(self, name: str, command_template: str, **kwargs):
        super().__init__(name=name, **kwargs)
        self.command_template = command_template

    def from_input(self, raw: str | bytes) -> str:
        if not isinstance(raw, (str, bytes)):
            raise TypeError(
                f"{self.name} expected str or bytes input, got {type(raw).__name__}"
            )
        return raw.strip() if isinstance(raw, str) else raw.decode("utf-8").strip()

    async def _run(self, parsed_input: str) -> str:
        # Replace placeholder in template, or use raw input as full command
        command = self.command_template.format(parsed_input)
        result = subprocess.run(command, shell=True, text=True, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def to_output(self, result: str) -> str:
        return result

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.GREEN_b}]⚙ ShellAction[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_into}')[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))

    def __str__(self):
        return (
            f"ShellAction(name={self.name!r}, command_template={self.command_template!r})"
        )
