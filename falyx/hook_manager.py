# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""hook_manager.py"""
from __future__ import annotations

import inspect
from enum import Enum
from typing import Awaitable, Callable, Dict, List, Optional, Union

from falyx.context import ExecutionContext
from falyx.utils import logger

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
    def choices(cls) -> List[HookType]:
        """Return a list of all hook type choices."""
        return list(cls)

    def __str__(self) -> str:
        """Return the string representation of the hook type."""
        return self.value


class HookManager:
    def __init__(self) -> None:
        self._hooks: Dict[HookType, List[Hook]] = {
            hook_type: [] for hook_type in HookType
        }

    def register(self, hook_type: HookType, hook: Hook):
        if hook_type not in HookType:
            raise ValueError(f"Unsupported hook type: {hook_type}")
        self._hooks[hook_type].append(hook)

    def clear(self, hook_type: Optional[HookType] = None):
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
                    f"⚠️ Hook '{hook.__name__}' raised an exception during '{hook_type}'"
                    f" for '{context.name}': {hook_error}"
                )

                if hook_type == HookType.ON_ERROR:
                    assert isinstance(
                        context.exception, Exception
                    ), "Context exception should be set for ON_ERROR hook"
                    raise context.exception from hook_error
