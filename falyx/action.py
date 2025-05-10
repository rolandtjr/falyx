# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""action.py

Core action system for Falyx.

This module defines the building blocks for executable actions and workflows,
providing a structured way to compose, execute, recover, and manage sequences of operations.

All actions are callable and follow a unified signature:
    result = action(*args, **kwargs)

Core guarantees:
- Full hook lifecycle support (before, on_success, on_error, after, on_teardown).
- Consistent timing and execution context tracking for each run.
- Unified, predictable result handling and error propagation.
- Optional last_result injection to enable flexible, data-driven workflows.
- Built-in support for retries, rollbacks, parallel groups, chaining, and fallback recovery.

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

import asyncio
import random
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor
from functools import cached_property, partial
from typing import Any, Callable

from rich.console import Console
from rich.tree import Tree

from falyx.context import ExecutionContext, SharedContext
from falyx.debug import register_debug_hooks
from falyx.exceptions import EmptyChainError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.options_manager import OptionsManager
from falyx.retry import RetryHandler, RetryPolicy
from falyx.themes.colors import OneColors
from falyx.utils import ensure_async, logger


class BaseAction(ABC):
    """
    Base class for actions. Actions can be simple functions or more
    complex actions like `ChainedAction` or `ActionGroup`. They can also
    be run independently or as part of Falyx.

    inject_last_result (bool): Whether to inject the previous action's result into kwargs.
    inject_into (str): The name of the kwarg key to inject the result as
                                 (default: 'last_result').
    _requires_injection (bool): Whether the action requires input injection.
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
        self._requires_injection: bool = False
        self._skip_in_chain: bool = False
        self.console = Console(color_system="auto")
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

    def set_options_manager(self, options_manager: OptionsManager) -> None:
        self.options_manager = options_manager

    def set_shared_context(self, shared_context: SharedContext) -> None:
        self.shared_context = shared_context

    def get_option(self, option_name: str, default: Any = None) -> Any:
        """Resolve an option from the OptionsManager if present, otherwise use the fallback."""
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
                logger.warning("[%s] ⚠️ Overriding '%s' with last_result", self.name, key)
            kwargs = dict(kwargs)
            kwargs[key] = self.shared_context.last_result()
        return kwargs

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        self.hooks.register(hook_type, hook)

    async def _write_stdout(self, data: str) -> None:
        """Override in subclasses that produce terminal output."""

    def requires_io_injection(self) -> bool:
        """Checks to see if the action requires input injection."""
        return self._requires_injection

    def __repr__(self) -> str:
        return str(self)


class Action(BaseAction):
    """
    Action wraps a simple function or coroutine into a standard executable unit.

    It supports:
    - Optional retry logic.
    - Hook lifecycle (before, success, error, after, teardown).
    - Last result injection for chaining.
    - Optional rollback handlers for undo logic.

    Args:
        name (str): Name of the action.
        action (Callable): The function or coroutine to execute.
        rollback (Callable, optional): Rollback function to undo the action.
        args (tuple, optional): Static positional arguments.
        kwargs (dict, optional): Static keyword arguments.
        hooks (HookManager, optional): Hook manager for lifecycle events.
        inject_last_result (bool, optional): Enable last_result injection.
        inject_into (str, optional): Name of injected key.
        retry (bool, optional): Enable retry logic.
        retry_policy (RetryPolicy, optional): Retry settings.
    """

    def __init__(
        self,
        name: str,
        action: Callable[..., Any],
        *,
        rollback: Callable[..., Any] | None = None,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        hooks: HookManager | None = None,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        retry: bool = False,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        super().__init__(
            name,
            hooks=hooks,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
        )
        self.action = action
        self.rollback = rollback
        self.args = args
        self.kwargs = kwargs or {}
        self.is_retryable = True
        self.retry_policy = retry_policy or RetryPolicy()
        if retry or (retry_policy and retry_policy.enabled):
            self.enable_retry()

    @property
    def action(self) -> Callable[..., Any]:
        return self._action

    @action.setter
    def action(self, value: Callable[..., Any]):
        self._action = ensure_async(value)

    @property
    def rollback(self) -> Callable[..., Any] | None:
        return self._rollback

    @rollback.setter
    def rollback(self, value: Callable[..., Any] | None):
        if value is None:
            self._rollback = None
        else:
            self._rollback = ensure_async(value)

    def enable_retry(self):
        """Enable retry with the existing retry policy."""
        self.retry_policy.enable_policy()
        logger.debug("[%s] Registering retry handler", self.name)
        handler = RetryHandler(self.retry_policy)
        self.hooks.register(HookType.ON_ERROR, handler.retry_on_error)

    def set_retry_policy(self, policy: RetryPolicy):
        """Set a new retry policy and re-register the handler."""
        self.retry_policy = policy
        if policy.enabled:
            self.enable_retry()

    async def _run(self, *args, **kwargs) -> Any:
        combined_args = args + self.args
        combined_kwargs = self._maybe_inject_last_result({**self.kwargs, **kwargs})

        context = ExecutionContext(
            name=self.name,
            args=combined_args,
            kwargs=combined_kwargs,
            action=self,
        )

        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            result = await self.action(*combined_args, **combined_kwargs)
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return context.result
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            if context.result is not None:
                logger.info("[%s] ✅ Recovered: %s", self.name, self.name)
                return context.result
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.GREEN_b}]⚙ Action[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_into}')[/dim]")
        if self.retry_policy.enabled:
            label.append(
                f"\n[dim]↻ Retries:[/] {self.retry_policy.max_retries}x, "
                f"delay {self.retry_policy.delay}s, backoff {self.retry_policy.backoff}x"
            )

        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))

    def __str__(self):
        return (
            f"Action(name={self.name!r}, action={getattr(self._action, '__name__', repr(self._action))}, "
            f"args={self.args!r}, kwargs={self.kwargs!r}, retry={self.retry_policy.enabled})"
        )


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

        async def literal(*args, **kwargs):
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


class FallbackAction(Action):
    """
    FallbackAction provides a default value if the previous action failed or returned None.

    It injects the last result and checks:
    - If last_result is not None, it passes it through unchanged.
    - If last_result is None (e.g., due to failure), it replaces it with a fallback value.

    Used in ChainedAction pipelines to gracefully recover from errors or missing data.
    When activated, it consumes the preceding error and allows the chain to continue normally.

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


class ActionListMixin:
    """Mixin for managing a list of actions."""

    def __init__(self) -> None:
        self.actions: list[BaseAction] = []

    def set_actions(self, actions: list[BaseAction]) -> None:
        """Replaces the current action list with a new one."""
        self.actions.clear()
        for action in actions:
            self.add_action(action)

    def add_action(self, action: BaseAction) -> None:
        """Adds an action to the list."""
        self.actions.append(action)

    def remove_action(self, name: str) -> None:
        """Removes an action by name."""
        self.actions = [action for action in self.actions if action.name != name]

    def has_action(self, name: str) -> bool:
        """Checks if an action with the given name exists."""
        return any(action.name == name for action in self.actions)

    def get_action(self, name: str) -> BaseAction | None:
        """Retrieves an action by name."""
        for action in self.actions:
            if action.name == name:
                return action
        return None


class ChainedAction(BaseAction, ActionListMixin):
    """
    ChainedAction executes a sequence of actions one after another.

    Features:
    - Supports optional automatic last_result injection (auto_inject).
    - Recovers from intermediate errors using FallbackAction if present.
    - Rolls back all previously executed actions if a failure occurs.
    - Handles literal values with LiteralInputAction.

    Best used for defining robust, ordered workflows where each step can depend on previous results.

    Args:
        name (str): Name of the chain.
        actions (list): List of actions or literals to execute.
        hooks (HookManager, optional): Hooks for lifecycle events.
        inject_last_result (bool, optional): Whether to inject last results into kwargs by default.
        inject_into (str, optional): Key name for injection.
        auto_inject (bool, optional): Auto-enable injection for subsequent actions.
        return_list (bool, optional): Whether to return a list of all results. False returns the last result.
    """

    def __init__(
        self,
        name: str,
        actions: list[BaseAction | Any] | None = None,
        *,
        hooks: HookManager | None = None,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        auto_inject: bool = False,
        return_list: bool = False,
    ) -> None:
        super().__init__(
            name,
            hooks=hooks,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
        )
        ActionListMixin.__init__(self)
        self.auto_inject = auto_inject
        self.return_list = return_list
        if actions:
            self.set_actions(actions)

    def _wrap_if_needed(self, action: BaseAction | Any) -> BaseAction:
        if isinstance(action, BaseAction):
            return action
        elif callable(action):
            return Action(name=action.__name__, action=action)
        else:
            return LiteralInputAction(action)

    def add_action(self, action: BaseAction | Any) -> None:
        action = self._wrap_if_needed(action)
        if self.actions and self.auto_inject and not action.inject_last_result:
            action.inject_last_result = True
        super().add_action(action)
        if hasattr(action, "register_teardown") and callable(action.register_teardown):
            action.register_teardown(self.hooks)

    async def _run(self, *args, **kwargs) -> list[Any]:
        if not self.actions:
            raise EmptyChainError(f"[{self.name}] No actions to execute.")

        shared_context = SharedContext(name=self.name)
        if self.shared_context:
            shared_context.add_result(self.shared_context.last_result())
        updated_kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=updated_kwargs,
            action=self,
            extra={"results": [], "rollback_stack": []},
            shared_context=shared_context,
        )
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            for index, action in enumerate(self.actions):
                if action._skip_in_chain:
                    logger.debug(
                        "[%s] ⚠️ Skipping consumed action '%s'", self.name, action.name
                    )
                    continue
                shared_context.current_index = index
                prepared = action.prepare(shared_context, self.options_manager)
                last_result = shared_context.last_result()
                try:
                    if self.requires_io_injection() and last_result is not None:
                        result = await prepared(**{prepared.inject_into: last_result})
                    else:
                        result = await prepared(*args, **updated_kwargs)
                except Exception as error:
                    if index + 1 < len(self.actions) and isinstance(
                        self.actions[index + 1], FallbackAction
                    ):
                        logger.warning(
                            "[%s] ⚠️ Fallback triggered: %s, recovering with fallback '%s'.",
                            self.name,
                            error,
                            self.actions[index + 1].name,
                        )
                        shared_context.add_result(None)
                        context.extra["results"].append(None)
                        fallback = self.actions[index + 1].prepare(shared_context)
                        result = await fallback()
                        fallback._skip_in_chain = True
                    else:
                        raise
                shared_context.add_result(result)
                context.extra["results"].append(result)
                context.extra["rollback_stack"].append(prepared)

            all_results = context.extra["results"]
            assert (
                all_results
            ), f"[{self.name}] No results captured. Something seriously went wrong."
            context.result = all_results if self.return_list else all_results[-1]
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return context.result

        except Exception as error:
            context.exception = error
            shared_context.add_error(shared_context.current_index, error)
            await self._rollback(context.extra["rollback_stack"], *args, **kwargs)
            await self.hooks.trigger(HookType.ON_ERROR, context)
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def _rollback(self, rollback_stack, *args, **kwargs):
        """
        Roll back all executed actions in reverse order.

        Rollbacks run even if a fallback recovered from failure,
        ensuring consistent undo of all side effects.

        Actions without rollback handlers are skipped.

        Args:
            rollback_stack (list): Actions to roll back.
            *args, **kwargs: Passed to rollback handlers.
        """
        for action in reversed(rollback_stack):
            rollback = getattr(action, "rollback", None)
            if rollback:
                try:
                    logger.warning("[%s] ↩️ Rolling back...", action.name)
                    await action.rollback(*args, **kwargs)
                except Exception as error:
                    logger.error("[%s] ⚠️ Rollback failed: %s", action.name, error)

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        self.hooks.register(hook_type, hook)
        for action in self.actions:
            action.register_hooks_recursively(hook_type, hook)

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.CYAN_b}]⛓ ChainedAction[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_into}')[/dim]")
        tree = parent.add("".join(label)) if parent else Tree("".join(label))
        for action in self.actions:
            await action.preview(parent=tree)
        if not parent:
            self.console.print(tree)

    def __str__(self):
        return (
            f"ChainedAction(name={self.name!r}, actions={[a.name for a in self.actions]!r}, "
            f"auto_inject={self.auto_inject}, return_list={self.return_list})"
        )


class ActionGroup(BaseAction, ActionListMixin):
    """
    ActionGroup executes multiple actions concurrently in parallel.

    It is ideal for independent tasks that can be safely run simultaneously,
    improving overall throughput and responsiveness of workflows.

    Core features:
    - Parallel execution of all contained actions.
    - Shared last_result injection across all actions if configured.
    - Aggregated collection of individual results as (name, result) pairs.
    - Hook lifecycle support (before, on_success, on_error, after, on_teardown).
    - Error aggregation: captures all action errors and reports them together.

    Behavior:
    - If any action fails, the group collects the errors but continues executing
      other actions without interruption.
    - After all actions complete, ActionGroup raises a single exception summarizing
      all failures, or returns all results if successful.

    Best used for:
    - Batch processing multiple independent tasks.
    - Reducing latency for workflows with parallelizable steps.
    - Isolating errors while maximizing successful execution.

    Args:
        name (str): Name of the chain.
        actions (list): List of actions or literals to execute.
        hooks (HookManager, optional): Hooks for lifecycle events.
        inject_last_result (bool, optional): Whether to inject last results into kwargs by default.
        inject_into (str, optional): Key name for injection.
    """

    def __init__(
        self,
        name: str,
        actions: list[BaseAction] | None = None,
        *,
        hooks: HookManager | None = None,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
    ):
        super().__init__(
            name,
            hooks=hooks,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
        )
        ActionListMixin.__init__(self)
        if actions:
            self.set_actions(actions)

    def _wrap_if_needed(self, action: BaseAction | Any) -> BaseAction:
        if isinstance(action, BaseAction):
            return action
        elif callable(action):
            return Action(name=action.__name__, action=action)
        else:
            raise TypeError(
                f"ActionGroup only accepts BaseAction or callable, got {type(action).__name__}"
            )

    def add_action(self, action: BaseAction | Any) -> None:
        action = self._wrap_if_needed(action)
        super().add_action(action)
        if hasattr(action, "register_teardown") and callable(action.register_teardown):
            action.register_teardown(self.hooks)

    async def _run(self, *args, **kwargs) -> list[tuple[str, Any]]:
        shared_context = SharedContext(name=self.name, is_parallel=True)
        if self.shared_context:
            shared_context.set_shared_result(self.shared_context.last_result())
        updated_kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=updated_kwargs,
            action=self,
            extra={"results": [], "errors": []},
            shared_context=shared_context,
        )

        async def run_one(action: BaseAction):
            try:
                prepared = action.prepare(shared_context, self.options_manager)
                result = await prepared(*args, **updated_kwargs)
                shared_context.add_result((action.name, result))
                context.extra["results"].append((action.name, result))
            except Exception as error:
                shared_context.add_error(shared_context.current_index, error)
                context.extra["errors"].append((action.name, error))

        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            await asyncio.gather(*[run_one(a) for a in self.actions])

            if context.extra["errors"]:
                context.exception = Exception(
                    f"{len(context.extra['errors'])} action(s) failed: "
                    f"{' ,'.join(name for name, _ in context.extra["errors"])}"
                )
                await self.hooks.trigger(HookType.ON_ERROR, context)
                raise context.exception

            context.result = context.extra["results"]
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return context.result

        except Exception as error:
            context.exception = error
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        super().register_hooks_recursively(hook_type, hook)
        for action in self.actions:
            action.register_hooks_recursively(hook_type, hook)

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.MAGENTA_b}]⏩ ActionGroup (parallel)[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](receives '{self.inject_into}')[/dim]")
        tree = parent.add("".join(label)) if parent else Tree("".join(label))
        actions = self.actions.copy()
        random.shuffle(actions)
        await asyncio.gather(*(action.preview(parent=tree) for action in actions))
        if not parent:
            self.console.print(tree)

    def __str__(self):
        return (
            f"ActionGroup(name={self.name!r}, actions={[a.name for a in self.actions]!r}, "
            f"inject_last_result={self.inject_last_result})"
        )


class ProcessAction(BaseAction):
    """
    ProcessAction runs a function in a separate process using ProcessPoolExecutor.

    Features:
    - Executes CPU-bound or blocking tasks without blocking the main event loop.
    - Supports last_result injection into the subprocess.
    - Validates that last_result is pickleable when injection is enabled.

    Args:
        name (str): Name of the action.
        func (Callable): Function to execute in a new process.
        args (tuple, optional): Positional arguments.
        kwargs (dict, optional): Keyword arguments.
        hooks (HookManager, optional): Hook manager for lifecycle events.
        executor (ProcessPoolExecutor, optional): Custom executor if desired.
        inject_last_result (bool, optional): Inject last result into the function.
        inject_into (str, optional): Name of the injected key.
    """

    def __init__(
        self,
        name: str,
        action: Callable[..., Any],
        *,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        hooks: HookManager | None = None,
        executor: ProcessPoolExecutor | None = None,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
    ):
        super().__init__(
            name,
            hooks=hooks,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
        )
        self.action = action
        self.args = args
        self.kwargs = kwargs or {}
        self.executor = executor or ProcessPoolExecutor()
        self.is_retryable = True

    async def _run(self, *args, **kwargs):
        if self.inject_last_result:
            last_result = self.shared_context.last_result()
            if not self._validate_pickleable(last_result):
                raise ValueError(
                    f"Cannot inject last result into {self.name}: "
                    f"last result is not pickleable."
                )
        combined_args = args + self.args
        combined_kwargs = self._maybe_inject_last_result({**self.kwargs, **kwargs})
        context = ExecutionContext(
            name=self.name,
            args=combined_args,
            kwargs=combined_kwargs,
            action=self,
        )
        loop = asyncio.get_running_loop()

        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            result = await loop.run_in_executor(
                self.executor, partial(self.action, *combined_args, **combined_kwargs)
            )
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return result
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            if context.result is not None:
                return context.result
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    def _validate_pickleable(self, obj: Any) -> bool:
        try:
            import pickle

            pickle.dumps(obj)
            return True
        except (pickle.PicklingError, TypeError):
            return False

    async def preview(self, parent: Tree | None = None):
        label = [
            f"[{OneColors.DARK_YELLOW_b}]🧠 ProcessAction (new process)[/] '{self.name}'"
        ]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_into}')[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))

    def __str__(self) -> str:
        return (
            f"ProcessAction(name={self.name!r}, action={getattr(self.action, '__name__', repr(self.action))}, "
            f"args={self.args!r}, kwargs={self.kwargs!r})"
        )
