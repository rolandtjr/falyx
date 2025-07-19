# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `LiteralInputAction`, a lightweight Falyx Action that injects a static,
predefined value into a `ChainedAction` workflow.

This Action is useful for embedding literal values (e.g., strings, numbers,
dicts) as part of a CLI pipeline without writing custom callables. It behaves
like a constant-returning function that can serve as the starting point,
fallback, or manual override within a sequence of actions.

Key Features:
- Wraps any static value as a Falyx-compatible Action
- Fully hookable and previewable like any other Action
- Enables declarative workflows with no required user input
- Compatible with auto-injection and shared context in `ChainedAction`

Common Use Cases:
- Supplying default parameters or configuration values mid-pipeline
- Starting a chain with a fixed value (e.g., base URL, credentials)
- Bridging gaps between conditional or dynamically generated Actions

Example:
    ChainedAction(
        name="SendStaticMessage",
        actions=[
            LiteralInputAction("hello world"),
            SendMessageAction(),
        ]
    )

The `LiteralInputAction` is a foundational building block for pipelines that
require predictable, declarative value injection at any stage.
"""
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
