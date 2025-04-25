"""action.py

Any Action or Command is callable and supports the signature:
    result = thing(*args, **kwargs)

This guarantees:
- Hook lifecycle (before/after/error/teardown)
- Timing
- Consistent return values
"""
from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any, Callable

from rich.console import Console
from rich.tree import Tree

from falyx.context import ExecutionContext, ResultsContext
from falyx.debug import register_debug_hooks
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.retry import RetryHandler, RetryPolicy
from falyx.themes.colors import OneColors
from falyx.utils import ensure_async, logger

console = Console()


class BaseAction(ABC):
    """
    Base class for actions. Actions can be simple functions or more
    complex actions like `ChainedAction` or `ActionGroup`. They can also
    be run independently or as part of Menu.

    inject_last_result (bool): Whether to inject the previous action's result into kwargs.
    inject_last_result_as (str): The name of the kwarg key to inject the result as
                                 (default: 'last_result').
    """
    def __init__(
            self,
            name: str,
            hooks: HookManager | None = None,
            inject_last_result: bool = False,
            inject_last_result_as: str = "last_result",
            logging_hooks: bool = False,
    ) -> None:
        self.name = name
        self.hooks = hooks or HookManager()
        self.is_retryable: bool = False
        self.results_context: ResultsContext | None = None
        self.inject_last_result: bool = inject_last_result
        self.inject_last_result_as: str = inject_last_result_as
        self.requires_injection: bool = False

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

    def set_results_context(self, results_context: ResultsContext):
        self.results_context = results_context

    def prepare_for_chain(self, results_context: ResultsContext) -> BaseAction:
        """
        Prepare the action specifically for sequential (ChainedAction) execution.
        Can be overridden for chain-specific logic.
        """
        self.set_results_context(results_context)
        return self

    def prepare_for_group(self, results_context: ResultsContext) -> BaseAction:
        """
        Prepare the action specifically for parallel (ActionGroup) execution.
        Can be overridden for group-specific logic.
        """
        self.set_results_context(results_context)
        return self

    def _maybe_inject_last_result(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        if self.inject_last_result and self.results_context:
            key = self.inject_last_result_as
            if key in kwargs:
                logger.warning("[%s] ⚠️ Overriding '%s' with last_result", self.name, key)
            kwargs = dict(kwargs)
            kwargs[key] = self.results_context.last_result()
        return kwargs

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        self.hooks.register(hook_type, hook)

    @classmethod
    def enable_retries_recursively(cls, action: BaseAction, policy: RetryPolicy | None):
        if not policy:
            policy = RetryPolicy(enabled=True)
        if isinstance(action, Action):
            action.retry_policy = policy
            action.retry_policy.enabled = True
            action.hooks.register(HookType.ON_ERROR, RetryHandler(policy).retry_on_error)

        if hasattr(action, "actions"):
            for sub in action.actions:
                cls.enable_retries_recursively(sub, policy)

    async def _write_stdout(self, data: str) -> None:
        """Override in subclasses that produce terminal output."""
        pass

    def requires_io_injection(self) -> bool:
        """Checks to see if the action requires input injection."""
        return self.requires_injection

    def __str__(self):
        return f"<{self.__class__.__name__} '{self.name}'>"

    def __repr__(self):
        return str(self)


class Action(BaseAction):
    """A simple action that runs a callable. It can be a function or a coroutine."""
    def __init__(
            self,
            name: str,
            action,
            rollback=None,
            args: tuple[Any, ...] = (),
            kwargs: dict[str, Any] | None = None,
            hooks: HookManager | None = None,
            inject_last_result: bool = False,
            inject_last_result_as: str = "last_result",
            retry: bool = False,
            retry_policy: RetryPolicy | None = None,
    ) -> None:
        super().__init__(name, hooks, inject_last_result, inject_last_result_as)
        self.action = ensure_async(action)
        self.rollback = rollback
        self.args = args
        self.kwargs = kwargs or {}
        self.is_retryable = True
        self.retry_policy = retry_policy or RetryPolicy()
        if retry or (retry_policy and retry_policy.enabled):
            self.enable_retry()

    def enable_retry(self):
        """Enable retry with the existing retry policy."""
        self.retry_policy.enabled = True
        logger.debug(f"[Action:{self.name}] Registering retry handler")
        handler = RetryHandler(self.retry_policy)
        self.hooks.register(HookType.ON_ERROR, handler.retry_on_error)

    def set_retry_policy(self, policy: RetryPolicy):
        """Set a new retry policy and re-register the handler."""
        self.retry_policy = policy
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
            raise error
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.GREEN_b}]⚙ Action[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_last_result_as}')[/dim]")
        if self.retry_policy.enabled:
            label.append(
                f"\n[dim]↻ Retries:[/] {self.retry_policy.max_retries}x, "
                f"delay {self.retry_policy.delay}s, backoff {self.retry_policy.backoff}x"
            )

        if parent:
            parent.add("".join(label))
        else:
            console.print(Tree("".join(label)))


class LiteralInputAction(Action):
    def __init__(self, value: Any):
        async def literal(*args, **kwargs):
            return value
        super().__init__("Input", literal, inject_last_result=True)


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
    """A ChainedAction is a sequence of actions that are executed in order."""
    def __init__(
            self,
            name: str,
            actions: list[BaseAction | Any] | None = None,
            hooks: HookManager | None = None,
            inject_last_result: bool = False,
            inject_last_result_as: str = "last_result",
            auto_inject: bool = False,
    ) -> None:
        super().__init__(name, hooks, inject_last_result, inject_last_result_as)
        ActionListMixin.__init__(self)
        self.auto_inject = auto_inject
        if actions:
            self.set_actions(actions)

    def _wrap_literal_if_needed(self, action: BaseAction | Any) -> BaseAction:
        return LiteralInputAction(action) if not isinstance(action, BaseAction) else action

    def _apply_auto_inject(self, action: BaseAction) -> None:
        if self.auto_inject and not action.inject_last_result:
            action.inject_last_result = True

    def set_actions(self, actions: list[BaseAction | Any]):
        self.actions.clear()
        for action in actions:
            action = self._wrap_literal_if_needed(action)
            self._apply_auto_inject(action)
            self.add_action(action)

    async def _run(self, *args, **kwargs) -> list[Any]:
        results_context = ResultsContext(name=self.name)
        if self.results_context:
            results_context.add_result(self.results_context.last_result())
        updated_kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=updated_kwargs,
            action=self,
            extra={"results": [], "rollback_stack": []},
        )
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            for index, action in enumerate(self.actions):
                results_context.current_index = index
                prepared = action.prepare_for_chain(results_context)
                last_result = results_context.last_result()
                if self.requires_io_injection() and last_result is not None:
                    result = await prepared(**{prepared.inject_last_result_as: last_result})
                else:
                    result = await prepared(*args, **updated_kwargs)
                results_context.add_result(result)
                context.extra["results"].append(result)
                context.extra["rollback_stack"].append(prepared)

            context.result = context.extra["results"]
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return context.result

        except Exception as error:
            context.exception = error
            results_context.errors.append((results_context.current_index, error))
            await self._rollback(context.extra["rollback_stack"], *args, **kwargs)
            await self.hooks.trigger(HookType.ON_ERROR, context)
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def _rollback(self, rollback_stack, *args, **kwargs):
        for action in reversed(rollback_stack):
            rollback = getattr(action, "rollback", None)
            if rollback:
                try:
                    logger.warning("[%s] ↩️ Rolling back...", action.name)
                    await action.rollback(*args, **kwargs)
                except Exception as error:
                    logger.error("[%s]⚠️ Rollback failed: %s", action.name, error)

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.CYAN_b}]⛓ ChainedAction[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_last_result_as}')[/dim]")
        tree = parent.add("".join(label)) if parent else Tree("".join(label))
        for action in self.actions:
            await action.preview(parent=tree)
        if not parent:
            console.print(tree)

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        self.hooks.register(hook_type, hook)
        for action in self.actions:
            action.register_hooks_recursively(hook_type, hook)


class ActionGroup(BaseAction, ActionListMixin):
    """An ActionGroup is a collection of actions that can be run in parallel."""
    def __init__(
            self,
            name: str,
            actions: list[BaseAction] | None = None,
            hooks: HookManager | None = None,
            inject_last_result: bool = False,
            inject_last_result_as: str = "last_result",
    ):
        super().__init__(name, hooks, inject_last_result, inject_last_result_as)
        ActionListMixin.__init__(self)
        if actions:
            self.set_actions(actions)

    async def _run(self, *args, **kwargs) -> list[tuple[str, Any]]:
        results_context = ResultsContext(name=self.name, is_parallel=True)
        if self.results_context:
            results_context.set_shared_result(self.results_context.last_result())
        updated_kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=updated_kwargs,
            action=self,
            extra={"results": [], "errors": []},
        )
        async def run_one(action: BaseAction):
            try:
                prepared = action.prepare_for_group(results_context)
                result = await prepared(*args, **updated_kwargs)
                results_context.add_result((action.name, result))
                context.extra["results"].append((action.name, result))
            except Exception as error:
                results_context.errors.append((results_context.current_index, error))
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

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.MAGENTA_b}]⏩ ActionGroup (parallel)[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](receives '{self.inject_last_result_as}')[/dim]")
        tree = parent.add("".join(label)) if parent else Tree("".join(label))
        actions = self.actions.copy()
        random.shuffle(actions)
        await asyncio.gather(*(action.preview(parent=tree) for action in actions))
        if not parent:
            console.print(tree)

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        super().register_hooks_recursively(hook_type, hook)
        for action in self.actions:
            action.register_hooks_recursively(hook_type, hook)


class ProcessAction(BaseAction):
    """A ProcessAction runs a function in a separate process using ProcessPoolExecutor."""
    def __init__(
        self,
        name: str,
        func: Callable[..., Any],
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        hooks: HookManager | None = None,
        executor: ProcessPoolExecutor | None = None,
        inject_last_result: bool = False,
        inject_last_result_as: str = "last_result",
    ):
        super().__init__(name, hooks, inject_last_result, inject_last_result_as)
        self.func = func
        self.args = args
        self.kwargs = kwargs or {}
        self.executor = executor or ProcessPoolExecutor()
        self.is_retryable = True

    async def _run(self, *args, **kwargs):
        if self.inject_last_result:
            last_result = self.results_context.last_result()
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
                self.executor, partial(self.func, *combined_args, **combined_kwargs)
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

    async def preview(self, parent: Tree | None = None):
        label = [f"[{OneColors.DARK_YELLOW_b}]🧠 ProcessAction (new process)[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](injects '{self.inject_last_result_as}')[/dim]")
        if parent:
            parent.add("".join(label))
        else:
            console.print(Tree("".join(label)))

    def _validate_pickleable(self, obj: Any) -> bool:
        try:
            import pickle
            pickle.dumps(obj)
            return True
        except (pickle.PicklingError, TypeError):
            return False
