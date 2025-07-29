# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `ProcessAction`, a Falyx Action that executes a blocking or CPU-bound function
in a separate process using `concurrent.futures.ProcessPoolExecutor`.

This is useful for offloading expensive computations or subprocess-compatible operations
from the main event loop, while maintaining Falyx's composable, hookable, and injectable
execution model.

`ProcessAction` mirrors the behavior of a normal `Action`, but ensures isolation from
the asyncio event loop and handles serialization (pickling) of arguments and injected
state.

Key Features:
- Runs a callable in a separate Python process
- Compatible with `last_result` injection for chained workflows
- Validates that injected values are pickleable before dispatch
- Supports hook lifecycle (`before`, `on_success`, `on_error`, etc.)
- Custom executor support for reuse or configuration

Use Cases:
- CPU-intensive operations (e.g., image processing, simulations, data transformations)
- Blocking third-party libraries that don't cooperate with asyncio
- CLI workflows that require subprocess-level parallelism or safety

Example:
    ProcessAction(
        name="ComputeChecksum",
        action=calculate_sha256,
        args=("large_file.bin",),
    )

Raises:
- `ValueError`: If an injected value is not pickleable
- `Exception`: Propagated from the subprocess on failure

This module enables structured offloading of workload in CLI pipelines while maintaining
full introspection and lifecycle management.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any, Callable

from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.themes import OneColors


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
        never_prompt: bool | None = None,
        logging_hooks: bool = False,
        spinner: bool = False,
        spinner_message: str = "Processing...",
        spinner_type: str = "dots",
        spinner_style: str = OneColors.CYAN,
        spinner_speed: float = 1.0,
    ):
        super().__init__(
            name,
            hooks=hooks,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
            never_prompt=never_prompt,
            logging_hooks=logging_hooks,
            spinner=spinner,
            spinner_message=spinner_message,
            spinner_type=spinner_type,
            spinner_style=spinner_style,
            spinner_speed=spinner_speed,
        )
        self.action = action
        self.args = args
        self.kwargs = kwargs or {}
        self.executor = executor or ProcessPoolExecutor()
        self.is_retryable = True

    def get_infer_target(self) -> tuple[Callable[..., Any] | None, None]:
        return self.action, None

    async def _run(self, *args, **kwargs) -> Any:
        if self.inject_last_result and self.shared_context:
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
            f"ProcessAction(name={self.name!r}, "
            f"action={getattr(self.action, '__name__', repr(self.action))}, "
            f"args={self.args!r}, kwargs={self.kwargs!r})"
        )
