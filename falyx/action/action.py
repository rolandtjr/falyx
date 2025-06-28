# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""action.py"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.logger import logger
from falyx.retry import RetryHandler, RetryPolicy
from falyx.themes import OneColors
from falyx.utils import ensure_async


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
        action: Callable[..., Any] | Callable[..., Awaitable[Any]],
        *,
        rollback: Callable[..., Any] | Callable[..., Awaitable[Any]] | None = None,
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
    def action(self) -> Callable[..., Awaitable[Any]]:
        return self._action

    @action.setter
    def action(self, value: Callable[..., Awaitable[Any]]):
        self._action = ensure_async(value)

    @property
    def rollback(self) -> Callable[..., Awaitable[Any]] | None:
        return self._rollback

    @rollback.setter
    def rollback(self, value: Callable[..., Awaitable[Any]] | None):
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

    def get_infer_target(self) -> tuple[Callable[..., Any], None]:
        """
        Returns the callable to be used for argument inference.
        By default, it returns the action itself.
        """
        return self.action, None

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
                logger.info("[%s] Recovered: %s", self.name, self.name)
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
            f"Action(name={self.name!r}, action="
            f"{getattr(self._action, '__name__', repr(self._action))}, "
            f"retry={self.retry_policy.enabled}, "
            f"rollback={self.rollback is not None})"
        )
