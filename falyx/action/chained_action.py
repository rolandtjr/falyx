# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `ChainedAction`, a core Falyx construct for executing a sequence of actions
in strict order, optionally injecting results from previous steps into subsequent ones.

`ChainedAction` is designed for linear workflows where each step may depend on
the output of the previous one. It supports rollback semantics, fallback recovery,
and advanced error handling using `SharedContext`. Literal values are supported via
automatic wrapping with `LiteralInputAction`.

Key Features:
- Executes a list of actions sequentially
- Optional `auto_inject` to forward `last_result` into each step
- Supports fallback recovery using `FallbackAction` when an error occurs
- Rollback stack to undo already-completed actions on failure
- Integrates with the full Falyx hook lifecycle
- Previews and introspects workflow structure via `Rich`

Use Cases:
- Ordered pipelines (e.g., build → test → deploy)
- Data transformations or ETL workflows
- Linear decision trees or interactive wizards

Special Behaviors:
- Literal inputs (e.g., strings, numbers) are converted to `LiteralInputAction`
- If an action raises and is followed by a `FallbackAction`, it will be skipped and recovered
- If a `BreakChainSignal` is raised, the chain stops early and rollbacks are triggered

Raises:
- `EmptyChainError`: If no actions are present
- `BreakChainSignal`: When explicitly triggered by a child action
- `Exception`: For all unhandled failures during chained execution

Example:
    ChainedAction(
        name="DeployFlow",
        actions=[
            ActionGroup(
                name="PreDeploymentChecks",
                actions=[
                    Action(
                        name="ValidateInputs",
                        action=validate_inputs,
                    ),
                    Action(
                        name="CheckDependencies",
                        action=check_dependencies,
                    ),
                ],
            ),
            Action(
                name="BuildArtifact",
                action=build_artifact,
            ),
            Action(
                name="Upload",
                action=upload,
            ),
            Action(
                name="NotifySuccess",
                action=notify_success,
            ),
        ],
        auto_inject=True,
    )
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Sequence

from rich.tree import Tree

from falyx.action.action import Action
from falyx.action.action_mixins import ActionListMixin
from falyx.action.base_action import BaseAction
from falyx.action.fallback_action import FallbackAction
from falyx.action.literal_input_action import LiteralInputAction
from falyx.context import ExecutionContext, SharedContext
from falyx.exceptions import EmptyChainError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.logger import logger
from falyx.options_manager import OptionsManager
from falyx.signals import BreakChainSignal
from falyx.themes import OneColors


class ChainedAction(BaseAction, ActionListMixin):
    """
    ChainedAction executes a sequence of actions one after another.

    Features:
    - Supports optional automatic last_result injection (auto_inject).
    - Recovers from intermediate errors using FallbackAction if present.
    - Rolls back all previously executed actions if a failure occurs.
    - Handles literal values with LiteralInputAction.

    Best used for defining robust, ordered workflows where each step can depend on
    previous results.

    Args:
        name (str): Name of the chain. Used for logging and debugging.
        actions (list): List of actions or literals to execute.
        args (tuple, optional): Positional arguments.
        kwargs (dict, optional): Keyword arguments.
        hooks (HookManager, optional): Hooks for lifecycle events.
        inject_last_result (bool, optional): Whether to inject last results into kwargs
                                             by default.
        inject_into (str, optional): Key name for injection.
        auto_inject (bool, optional): Auto-enable injection for subsequent actions.
        return_list (bool, optional): Whether to return a list of all results. False
                                      returns the last result.
    """

    def __init__(
        self,
        name: str,
        actions: (
            Sequence[BaseAction | Callable[..., Any] | Callable[..., Awaitable[Any]]]
            | None
        ) = None,
        *,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        hooks: HookManager | None = None,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        auto_inject: bool = False,
        return_list: bool = False,
        never_prompt: bool | None = None,
        logging_hooks: bool = False,
        spinner: bool = False,
        spinner_message: str = "Processing...",
        spinner_type: str = "dots",
        spinner_style: str = OneColors.CYAN,
        spinner_speed: float = 1.0,
    ) -> None:
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
        ActionListMixin.__init__(self)
        self.args = args
        self.kwargs = kwargs or {}
        self.auto_inject = auto_inject
        self.return_list = return_list
        if actions:
            self.set_actions(actions)

    def _wrap_if_needed(self, action: BaseAction | Callable[..., Any]) -> BaseAction:
        if isinstance(action, BaseAction):
            return action
        elif callable(action):
            return Action(name=action.__name__, action=action)
        else:
            return LiteralInputAction(action)

    def add_action(self, action: BaseAction | Callable[..., Any]) -> None:
        action = self._wrap_if_needed(action)
        if self.actions and self.auto_inject and not action.inject_last_result:
            action.inject_last_result = True
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
        if self.actions:
            return self.actions[0].get_infer_target()
        return None, None

    def _clear_args(self):
        return (), {}

    async def _run(self, *args, **kwargs) -> Any:
        if not self.actions:
            raise EmptyChainError(f"[{self.name}] No actions to execute.")

        combined_args = args + self.args
        combined_kwargs = {**self.kwargs, **kwargs}

        shared_context = SharedContext(name=self.name, action=self)
        if self.shared_context:
            shared_context.add_result(self.shared_context.last_result())
        updated_kwargs = self._maybe_inject_last_result(combined_kwargs)
        context = ExecutionContext(
            name=self.name,
            args=combined_args,
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
                        "[%s] Skipping consumed action '%s'", self.name, action.name
                    )
                    continue
                shared_context.current_index = index
                prepared = action.prepare(shared_context, self.options_manager)
                try:
                    result = await prepared(*combined_args, **updated_kwargs)
                except Exception as error:
                    if index + 1 < len(self.actions) and isinstance(
                        self.actions[index + 1], FallbackAction
                    ):
                        logger.warning(
                            "[%s] Fallback triggered: %s, recovering with fallback "
                            "'%s'.",
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
                context.extra["rollback_stack"].append(
                    (prepared, combined_args, updated_kwargs)
                )
                combined_args, updated_kwargs = self._clear_args()

            all_results = context.extra["results"]
            assert (
                all_results
            ), f"[{self.name}] No results captured. Something seriously went wrong."
            context.result = all_results if self.return_list else all_results[-1]
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return context.result
        except BreakChainSignal as error:
            logger.info("[%s] Chain broken: %s", self.name, error)
            context.exception = error
            shared_context.add_error(shared_context.current_index, error)
            await self._rollback(context.extra["rollback_stack"])
        except Exception as error:
            context.exception = error
            shared_context.add_error(shared_context.current_index, error)
            await self._rollback(context.extra["rollback_stack"])
            await self.hooks.trigger(HookType.ON_ERROR, context)
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def _rollback(
        self, rollback_stack: list[tuple[Action, tuple[Any, ...], dict[str, Any]]]
    ):
        """
        Roll back all executed actions in reverse order.

        Rollbacks run even if a fallback recovered from failure,
        ensuring consistent undo of all side effects.

        Actions without rollback handlers are skipped.

        Args:
            rollback_stack (list): Actions to roll back.
            *args, **kwargs: Passed to rollback handlers.
        """
        for action, args, kwargs in reversed(rollback_stack):
            rollback = getattr(action, "rollback", None)
            if rollback:
                try:
                    logger.warning("[%s] Rolling back...", action.name)
                    await rollback(*args, **kwargs)
                except Exception as error:
                    logger.error("[%s] Rollback failed: %s", action.name, error)

    def register_hooks_recursively(self, hook_type: HookType, hook: Hook):
        """Register a hook for all actions and sub-actions."""
        super().register_hooks_recursively(hook_type, hook)
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
            f"ChainedAction(name={self.name}, "
            f"actions={[a.name for a in self.actions]}, "
            f"args={self.args!r}, kwargs={self.kwargs!r}, "
            f"auto_inject={self.auto_inject}, return_list={self.return_list})"
        )
