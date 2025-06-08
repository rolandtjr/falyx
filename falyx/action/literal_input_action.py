# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""literal_input_action.py"""
from __future__ import annotations

from functools import cached_property
from typing import Any

from rich.tree import Tree

from falyx.action.action import Action
from falyx.themes import OneColors


class LiteralInputAction(Action):
    """
    LiteralInputAction injects a static value into a ChainedAction.

    This allows embedding hardcoded values mid-pipeline, useful when:
    - Providing default or fallback inputs.
    - Starting a pipeline with a fixed input.
    - Supplying missing context manually.

    Args:
        value (Any): The static value to inject.
    """

    def __init__(self, value: Any):
        self._value = value

        async def literal(*_, **__):
            return value

        super().__init__("Input", literal)

    @cached_property
    def value(self) -> Any:
        """Return the literal value."""
        return self._value

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.LIGHT_YELLOW}]📥 LiteralInput[/] '{self.name}'"]
        label.append(f" [dim](value = {repr(self.value)})[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))

    def __str__(self) -> str:
        return f"LiteralInputAction(value={self.value!r})"
