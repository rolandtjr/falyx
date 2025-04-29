# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""io_action.py"""
import asyncio
import subprocess
import sys
from typing import Any

from rich.console import Console
from rich.tree import Tree

from falyx.action import BaseAction
from falyx.context import ExecutionContext
from falyx.exceptions import FalyxError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.themes.colors import OneColors
from falyx.utils import logger

console = Console()


class BaseIOAction(BaseAction):
    def __init__(
        self,
        name: str,
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
        last_result = kwargs.pop(self.inject_last_result_as, None)

        data = await self._read_stdin()
        if data:
            return self.from_input(data)

        if last_result is not None:
            return last_result

        if self.inject_last_result and self.results_context:
            return self.results_context.last_result()

        logger.debug("[%s] No input provided and no last result found for injection.", self.name)
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
            label.append(f" [dim](injects '{self.inject_last_result_as}')[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            console.print(Tree("".join(label)))


class UppercaseIO(BaseIOAction):
    def from_input(self, raw: str | bytes) -> str:
        if not isinstance(raw, (str, bytes)):
            raise TypeError(f"{self.name} expected str or bytes input, got {type(raw).__name__}")
        return raw.strip() if isinstance(raw, str) else raw.decode("utf-8").strip()

    async def _run(self, parsed_input: str, *args, **kwargs) -> str:
        return parsed_input.upper()

    def to_output(self, data: str) -> str:
        return data + "\n"


class ShellAction(BaseIOAction):
    def __init__(self, name: str, command_template: str, **kwargs):
        super().__init__(name=name, **kwargs)
        self.command_template = command_template

    def from_input(self, raw: str | bytes) -> str:
        if not isinstance(raw, (str, bytes)):
            raise TypeError(f"{self.name} expected str or bytes input, got {type(raw).__name__}")
        return raw.strip() if isinstance(raw, str) else raw.decode("utf-8").strip()

    async def _run(self, parsed_input: str) -> str:
        # Replace placeholder in template, or use raw input ddas full command
        command = self.command_template.format(parsed_input)
        result = subprocess.run(
            command, shell=True, text=True, capture_output=True
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def to_output(self, result: str) -> str:
        return result

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.GREEN_b}]⚙ ShellAction[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_last_result_as}')[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            console.print(Tree("".join(label)))

class GrepAction(BaseIOAction):
    def __init__(self, name: str, pattern: str, **kwargs):
        super().__init__(name=name, **kwargs)
        self.pattern = pattern

    def from_input(self, raw: str | bytes) -> str:
        if not isinstance(raw, (str, bytes)):
            raise TypeError(f"{self.name} expected str or bytes input, got {type(raw).__name__}")
        return raw.strip() if isinstance(raw, str) else raw.decode("utf-8").strip()

    async def _run(self, parsed_input: str) -> str:
        command = ["grep", "-n", self.pattern]
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        stdout, stderr = process.communicate(input=parsed_input)
        if process.returncode == 1:
            return ""
        if process.returncode != 0:
            raise RuntimeError(stderr.strip())
        return stdout.strip()

    def to_output(self, result: str) -> str:
        return result

