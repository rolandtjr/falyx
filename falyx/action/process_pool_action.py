# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `ProcessPoolAction`, a parallelized action executor that distributes
tasks across multiple processes using Python's `concurrent.futures.ProcessPoolExecutor`.

This module enables structured execution of CPU-bound tasks in parallel while
retaining Falyx's core guarantees: lifecycle hooks, error isolation, execution context
tracking, and introspectable previews.

Key Components:
- ProcessTask: Lightweight wrapper for a task + args/kwargs
- ProcessPoolAction: Parallel action that runs tasks concurrently in separate processes

Use this module to accelerate workflows involving expensive computation or
external resources that benefit from true parallelism.
"""
from __future__ import annotations

import asyncio
import random
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Callable, Sequence

from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext, SharedContext
from falyx.exceptions import EmptyPoolError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.logger import logger
from falyx.parser.utils import same_argument_definitions
from falyx.themes import OneColors


@dataclass
class ProcessTask:
    """
    Represents a callable task with its arguments for parallel execution.

    This lightweight container is used to queue individual tasks for execution
    inside a `ProcessPoolAction`.

    Attributes:
        task (Callable): A function to execute.
        args (tuple): Positional arguments to pass to the function.
        kwargs (dict): Keyword arguments to pass to the function.

    Raises:
        TypeError: If `task` is not callable.
    """

    task: Callable[..., Any]
    args: tuple = ()
    kwargs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not callable(self.task):
            raise TypeError(f"Expected a callable task, got {type(self.task).__name__}")


class ProcessPoolAction(BaseAction):
    """
    Executes a set of independent tasks in parallel using a process pool.

    `ProcessPoolAction` is ideal for CPU-bound tasks that benefit from
    concurrent execution in separate processes. Each task is wrapped in a
    `ProcessTask` instance and executed in a `concurrent.futures.ProcessPoolExecutor`.

    Key Features:
    - Parallel, process-based execution
    - Hook lifecycle support across all stages
    - Supports argument injection (e.g., `last_result`)
    - Compatible with retry behavior and shared context propagation
    - Captures all task results (including exceptions) and records execution context

    Args:
        name (str): Name of the action. Used for logging and debugging.
        actions (Sequence[ProcessTask] | None): A list of tasks to run.
        hooks (HookManager | None): Optional hook manager for lifecycle events.
        executor (ProcessPoolExecutor | None): Custom executor instance (optional).
        inject_last_result (bool): Whether to inject the last result into task kwargs.
        inject_into (str): Name of the kwarg to use for injected result.

    Returns:
        list[Any]: A list of task results in submission order. Exceptions are preserved.

    Raises:
        EmptyPoolError: If no actions are registered.
        ValueError: If injected `last_result` is not pickleable.

    Example:
        ProcessPoolAction(
            name="ParallelTransforms",
            actions=[
                ProcessTask(func_a, args=(1,)),
                ProcessTask(func_b, kwargs={"x": 2}),
            ]
        )
    """

    def __init__(
        self,
        name: str,
        actions: Sequence[ProcessTask] | None = None,
        *,
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
        self.executor = executor or ProcessPoolExecutor()
        self.is_retryable = True
        self.actions: list[ProcessTask] = []
        if actions:
            self.set_actions(actions)

    def set_actions(self, actions: Sequence[ProcessTask]) -> None:
        """Replaces the current action list with a new one."""
        self.actions.clear()
        for action in actions:
            self.add_action(action)

    def add_action(self, action: ProcessTask) -> None:
        if not isinstance(action, ProcessTask):
            raise TypeError(f"Expected a ProcessTask, got {type(action).__name__}")
        self.actions.append(action)

    def get_infer_target(self) -> tuple[Callable[..., Any] | None, None]:
        arg_defs = same_argument_definitions([action.task for action in self.actions])
        if arg_defs:
            return self.actions[0].task, None
        logger.debug(
            "[%s] auto_args disabled: mismatched ProcessPoolAction arguments",
            self.name,
        )
        return None, None

    async def _run(self, *args, **kwargs) -> Any:
        if not self.actions:
            raise EmptyPoolError(f"[{self.name}] No actions to execute.")
        shared_context = SharedContext(name=self.name, action=self, is_parallel=True)
        if self.shared_context:
            shared_context.set_shared_result(self.shared_context.last_result())
        if self.inject_last_result and self.shared_context:
            last_result = self.shared_context.last_result()
            if not self._validate_pickleable(last_result):
                raise ValueError(
                    f"Cannot inject last result into {self.name}: "
                    f"last result is not pickleable."
                )
        updated_kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=self.name,
            args=args,
            kwargs=updated_kwargs,
            action=self,
        )
        loop = asyncio.get_running_loop()

        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            futures = [
                loop.run_in_executor(
                    self.executor,
                    partial(
                        task.task,
                        *(*args, *task.args),
                        **{**updated_kwargs, **task.kwargs},
                    ),
                )
                for task in self.actions
            ]
            results = await asyncio.gather(*futures, return_exceptions=True)
            context.result = results
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return results
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
        label = [f"[{OneColors.DARK_YELLOW_b}]🧠 ProcessPoolAction[/] '{self.name}'"]
        if self.inject_last_result:
            label.append(f" [dim](receives '{self.inject_into}')[/dim]")
        tree = parent.add("".join(label)) if parent else Tree("".join(label))
        actions = self.actions.copy()
        random.shuffle(actions)
        for action in actions:
            label = [
                f"[{OneColors.DARK_YELLOW_b}]  - {getattr(action.task, '__name__', repr(action.task))}[/] "
                f"[dim]({', '.join(map(repr, action.args))})[/]"
            ]
            if action.kwargs:
                label.append(
                    f" [dim]({', '.join(f'{k}={v!r}' for k, v in action.kwargs.items())})[/]"
                )
            tree.add("".join(label))

        if not parent:
            self.console.print(tree)

    def __str__(self) -> str:
        return (
            f"ProcessPoolAction(name={self.name!r}, "
            f"actions={[getattr(action.task, '__name__', repr(action.task)) for action in self.actions]}, "
            f"inject_last_result={self.inject_last_result}, "
            f"inject_into={self.inject_into!r})"
        )
