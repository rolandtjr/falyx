# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""action_group.py"""
import asyncio
import random
from typing import Any, Awaitable, Callable, Sequence

from rich.tree import Tree

from falyx.action.action import Action
from falyx.action.action_mixins import ActionListMixin
from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext, SharedContext
from falyx.exceptions import EmptyGroupError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.logger import logger
from falyx.options_manager import OptionsManager
from falyx.parser.utils import same_argument_definitions
from falyx.themes.colors import OneColors


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
        inject_last_result (bool, optional): Whether to inject last results into kwargs
                                             by default.
        inject_into (str, optional): Key name for injection.
    """

    def __init__(
        self,
        name: str,
        actions: (
            Sequence[BaseAction | Callable[..., Any] | Callable[..., Awaitable]] | None
        ) = None,
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

    def _wrap_if_needed(self, action: BaseAction | Callable[..., Any]) -> BaseAction:
        if isinstance(action, BaseAction):
            return action
        elif callable(action):
            return Action(name=action.__name__, action=action)
        else:
            raise TypeError(
                "ActionGroup only accepts BaseAction or callable, got "
                f"{type(action).__name__}"
            )

    def add_action(self, action: BaseAction | Callable[..., Any]) -> None:
        action = self._wrap_if_needed(action)
        super().add_action(action)
        if hasattr(action, "register_teardown") and callable(action.register_teardown):
            action.register_teardown(self.hooks)

    def set_actions(self, actions: Sequence[BaseAction | Callable[..., Any]]) -> None:
        """Replaces the current action list with a new one."""
        self.actions.clear()
        for action in actions:
            self.add_action(action)

    def set_options_manager(self, options_manager: OptionsManager) -> None:
        super().set_options_manager(options_manager)
        for action in self.actions:
            action.set_options_manager(options_manager)

    def get_infer_target(self) -> tuple[Callable[..., Any] | None, dict[str, Any] | None]:
        arg_defs = same_argument_definitions(self.actions)
        if arg_defs:
            return self.actions[0].get_infer_target()
        logger.debug(
            "[%s] auto_args disabled: mismatched ActionGroup arguments",
            self.name,
        )
        return None, None

    async def _run(self, *args, **kwargs) -> list[tuple[str, Any]]:
        if not self.actions:
            raise EmptyGroupError(f"[{self.name}] No actions to execute.")
        shared_context = SharedContext(name=self.name, action=self, is_parallel=True)
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
                    f"{' ,'.join(name for name, _ in context.extra['errors'])}"
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
            f"ActionGroup(name={self.name!r}, actions={[a.name for a in self.actions]!r},"
            f" inject_last_result={self.inject_last_result}, "
            f"inject_into={self.inject_into!r})"
        )
