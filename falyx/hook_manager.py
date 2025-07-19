# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines the `HookManager` and `HookType` used in the Falyx CLI framework to manage
execution lifecycle hooks around actions and commands.

The hook system enables structured callbacks for important stages in a Falyx action's
execution, such as before execution, after success, upon error, and teardown. These
can be used for logging, side effects, diagnostics, metrics, and rollback logic.

Key Components:
- HookType: Enum categorizing supported hook lifecycle stages
- HookManager: Core class for registering and invoking hooks during action execution
- Hook: Union of sync and async callables accepting an `ExecutionContext`

Usage:
    hooks = HookManager()
    hooks.register(HookType.BEFORE, log_before)
"""
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
    """
    Enum for supported hook lifecycle phases in Falyx.

    HookType is used to classify lifecycle events that can be intercepted
    with user-defined callbacks.

    Members:
        BEFORE: Run before the action is invoked.
        ON_SUCCESS: Run after successful completion.
        ON_ERROR: Run when an exception occurs.
        AFTER: Run after success or failure (always runs).
        ON_TEARDOWN: Run at the very end, for resource cleanup.

    Aliases:
        "success" → "on_success"
        "error" → "on_error"
        "teardown" → "on_teardown"

    Example:
        HookType("error") → HookType.ON_ERROR
    """

    BEFORE = "before"
    ON_SUCCESS = "on_success"
    ON_ERROR = "on_error"
    AFTER = "after"
    ON_TEARDOWN = "on_teardown"

    @classmethod
    def choices(cls) -> list[HookType]:
        """Return a list of all hook type choices."""
        return list(cls)

    @classmethod
    def _get_alias(cls, value: str) -> str:
        aliases = {
            "success": "on_success",
            "error": "on_error",
            "teardown": "on_teardown",
        }
        return aliases.get(value, value)

    @classmethod
    def _missing_(cls, value: object) -> HookType:
        if not isinstance(value, str):
            raise ValueError(f"Invalid {cls.__name__}: {value!r}")
        normalized = value.strip().lower()
        alias = cls._get_alias(normalized)
        for member in cls:
            if member.value == alias:
                return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid {cls.__name__}: '{value}'. Must be one of: {valid}")

    def __str__(self) -> str:
        """Return the string representation of the hook type."""
        return self.value


class HookManager:
    """
    Manages lifecycle hooks for a command or action.

    `HookManager` tracks user-defined callbacks to be run at key points in a command's
    lifecycle: before execution, on success, on error, after completion, and during
    teardown. Both sync and async hooks are supported.

    Methods:
        register(hook_type, hook): Register a callable for a given HookType.
        clear(hook_type): Remove hooks for one or all lifecycle stages.
        trigger(hook_type, context): Execute all hooks of a given type.

    Example:
        hooks = HookManager()
        hooks.register(HookType.BEFORE, my_logger)
    """

    def __init__(self) -> None:
        self._hooks: dict[HookType, list[Hook]] = {
            hook_type: [] for hook_type in HookType
        }

    def register(self, hook_type: HookType | str, hook: Hook):
        """
        Register a new hook for a given lifecycle phase.

        Args:
            hook_type (HookType | str): The hook category (e.g. "before", "on_success").
            hook (Callable): The hook function to register.

        Raises:
            ValueError: If the hook type is invalid.
        """
        hook_type = HookType(hook_type)
        self._hooks[hook_type].append(hook)

    def clear(self, hook_type: HookType | None = None):
        """
        Clear registered hooks for one or all hook types.

        Args:
            hook_type (HookType | None): If None, clears all hooks.
        """
        if hook_type:
            self._hooks[hook_type] = []
        else:
            for ht in self._hooks:
                self._hooks[ht] = []

    async def trigger(self, hook_type: HookType, context: ExecutionContext):
        """
        Invoke all hooks registered for a given lifecycle phase.

        Args:
            hook_type (HookType): The lifecycle phase to trigger.
            context (ExecutionContext): The execution context passed to each hook.

        Raises:
            Exception: Re-raises the original context.exception if a hook fails during
                       ON_ERROR. Other hook exceptions are logged and skipped.
        """
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
