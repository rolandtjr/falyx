# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""hook_manager.py"""
from __future__ import annotations

import inspect
from enum import Enum
from typing import Awaitable, Callable, Union

from falyx.context import ExecutionContext
from falyx.logger import logger

Hook = Union[
    Callable[[ExecutionContext], None], Callable[[ExecutionContext], Awaitable[None]]
]


class HookType(Enum):
    """Enum for hook types to categorize the hooks."""

    BEFORE = "before"
    ON_SUCCESS = "on_success"
    ON_ERROR = "on_error"
    AFTER = "after"
    ON_TEARDOWN = "on_teardown"

    @classmethod
    def choices(cls) -> list[HookType]:
        """Return a list of all hook type choices."""
        return list(cls)

    def __str__(self) -> str:
        """Return the string representation of the hook type."""
        return self.value


class HookManager:
    """HookManager"""

    def __init__(self) -> None:
        self._hooks: dict[HookType, list[Hook]] = {
            hook_type: [] for hook_type in HookType
        }

    def register(self, hook_type: HookType | str, hook: Hook):
        """Raises ValueError if the hook type is not supported."""
        if not isinstance(hook_type, HookType):
            hook_type = HookType(hook_type)
        self._hooks[hook_type].append(hook)

    def clear(self, hook_type: HookType | None = None):
        if hook_type:
            self._hooks[hook_type] = []
        else:
            for ht in self._hooks:
                self._hooks[ht] = []

    async def trigger(self, hook_type: HookType, context: ExecutionContext):
        if hook_type not in self._hooks:
            raise ValueError(f"Unsupported hook type: {hook_type}")
        for hook in self._hooks[hook_type]:
            try:
                if inspect.iscoroutinefunction(hook):
                    await hook(context)
                else:
                    hook(context)
            except Exception as hook_error:
                logger.warning(
                    "[Hook:%s] raised an exception during '%s' for '%s': %s",
                    hook.__name__,
                    hook_type,
                    context.name,
                    hook_error,
                )

                if hook_type == HookType.ON_ERROR:
                    assert isinstance(
                        context.exception, Exception
                    ), "Context exception should be set for ON_ERROR hook"
                    raise context.exception from hook_error

    def __str__(self) -> str:
        """Return a formatted string of registered hooks grouped by hook type."""

        def format_hook_list(hooks: list[Hook]) -> str:
            return ", ".join(h.__name__ for h in hooks) if hooks else "—"

        lines = ["<HookManager>"]
        for hook_type in HookType:
            hook_list = self._hooks.get(hook_type, [])
            lines.append(f"  {hook_type.value}: {format_hook_list(hook_list)}")
        return "\n".join(lines)
