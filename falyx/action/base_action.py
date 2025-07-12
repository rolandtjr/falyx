# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""base_action.py

Core action system for Falyx.

This module defines the building blocks for executable actions and workflows,
providing a structured way to compose, execute, recover, and manage sequences of
operations.

All actions are callable and follow a unified signature:
    result = action(*args, **kwargs)

Core guarantees:
- Full hook lifecycle support (before, on_success, on_error, after, on_teardown).
- Consistent timing and execution context tracking for each run.
- Unified, predictable result handling and error propagation.
- Optional last_result injection to enable flexible, data-driven workflows.
- Built-in support for retries, rollbacks, parallel groups, chaining, and fallback
  recovery.

Key components:
- Action: wraps a function or coroutine into a standard executable unit.
- ChainedAction: runs actions sequentially, optionally injecting last results.
- ActionGroup: runs actions in parallel and gathers results.
- ProcessAction: executes CPU-bound functions in a separate process.
- LiteralInputAction: injects static values into workflows.
- FallbackAction: gracefully recovers from failures or missing data.

This design promotes clean, fault-tolerant, modular CLI and automation systems.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from rich.console import Console
from rich.tree import Tree

from falyx.console import console
from falyx.context import SharedContext
from falyx.debug import register_debug_hooks
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.logger import logger
from falyx.options_manager import OptionsManager


class BaseAction(ABC):
    """
    Base class for actions. Actions can be simple functions or more
    complex actions like `ChainedAction` or `ActionGroup`. They can also
    be run independently or as part of Falyx.

    inject_last_result (bool): Whether to inject the previous action's result
                               into kwargs.
    inject_into (str): The name of the kwarg key to inject the result as
                       (default: 'last_result').
    """

    def __init__(
        self,
        name: str,
        *,
        hooks: HookManager | None = None,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        never_prompt: bool = False,
        logging_hooks: bool = False,
    ) -> None:
        self.name = name
        self.hooks = hooks or HookManager()
        self.is_retryable: bool = False
        self.shared_context: SharedContext | None = None
        self.inject_last_result: bool = inject_last_result
        self.inject_into: str = inject_into
        self._never_prompt: bool = never_prompt
        self._skip_in_chain: bool = False
        self.console: Console = console
        self.options_manager: OptionsManager | None = None

        if logging_hooks:
            register_debug_hooks(self.hooks)

    async def __call__(self, *args, **kwargs) -> Any:
        return await self._run(*args, **kwargs)

    @abstractmethod
    async def _run(self, *args, **kwargs) -> Any:
        raise NotImplementedError("_run must be implemented by subclasses")

    @abstractmethod
    async def preview(self, parent: Tree | None = None):
        raise NotImplementedError("preview must be implemented by subclasses")

    @abstractmethod
    def get_infer_target(self) -> tuple[Callable[..., Any] | None, dict[str, Any] | None]:
        """
        Returns the callable to be used for argument inference.
        By default, it returns None.
        """
        raise NotImplementedError("get_infer_target must be implemented by subclasses")

    def set_options_manager(self, options_manager: OptionsManager) -> None:
        self.options_manager = options_manager

    def set_shared_context(self, shared_context: SharedContext) -> None:
        self.shared_context = shared_context

    def get_option(self, option_name: str, default: Any = None) -> Any:
        """
        Resolve an option from the OptionsManager if present, otherwise use the fallback.
        """
        if self.options_manager:
            return self.options_manager.get(option_name, default)
        return default

    @property
    def last_result(self) -> Any:
        """Return the last result from the shared context."""
        if self.shared_context:
            return self.shared_context.last_result()
        return None

    @property
    def never_prompt(self) -> bool:
        return self.get_option("never_prompt", self._never_prompt)

    def prepare(
        self, shared_context: SharedContext, options_manager: OptionsManager | None = None
    ) -> BaseAction:
        """
        Prepare the action specifically for sequential (ChainedAction) execution.
        Can be overridden for chain-specific logic.
        """
        self.set_shared_context(shared_context)
        if options_manager:
            self.set_options_manager(options_manager)
        return self

    def _maybe_inject_last_result(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if self.inject_last_result and self.shared_context:
            key = self.inject_into
            if key in kwargs:
                logger.warning("[%s] Overriding '%s' with last_result", self.name, key)
            kwargs = dict(kwargs)
            kwargs[key] = self.shared_context.last_result()
        return kwargs

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        self.hooks.register(hook_type, hook)

    async def _write_stdout(self, data: str) -> None:
        """Override in subclasses that produce terminal output."""

    def __repr__(self) -> str:
        return str(self)
