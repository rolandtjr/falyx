# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""shell_action.py
Execute shell commands with input substitution."""

from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Any, Callable

from rich.tree import Tree

from falyx.action.io_action import BaseIOAction
from falyx.exceptions import FalyxError
from falyx.themes import OneColors


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
