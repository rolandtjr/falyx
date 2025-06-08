# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""fallback_action.py"""
from functools import cached_property
from typing import Any

from rich.tree import Tree

from falyx.action.action import Action
from falyx.themes import OneColors


class FallbackAction(Action):
    """
    FallbackAction provides a default value if the previous action failed or
    returned None.

    It injects the last result and checks:
    - If last_result is not None, it passes it through unchanged.
    - If last_result is None (e.g., due to failure), it replaces it with a fallback value.

    Used in ChainedAction pipelines to gracefully recover from errors or missing data.
    When activated, it consumes the preceding error and allows the chain to continue
    normally.

    Args:
        fallback (Any): The fallback value to use if last_result is None.
    """

    def __init__(self, fallback: Any):
        self._fallback = fallback

        async def _fallback_logic(last_result):
            return last_result if last_result is not None else fallback

        super().__init__(name="Fallback", action=_fallback_logic, inject_last_result=True)

    @cached_property
    def fallback(self) -> Any:
        """Return the fallback value."""
        return self._fallback

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.LIGHT_RED}]🛟 Fallback[/] '{self.name}'"]
        label.append(f" [dim](uses fallback = {repr(self.fallback)})[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))

    def __str__(self) -> str:
        return f"FallbackAction(fallback={self.fallback!r})"
