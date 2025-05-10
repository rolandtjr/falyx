from typing import Any

from rich.tree import Tree

from falyx.action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.protocols import ActionFactoryProtocol
from falyx.themes.colors import OneColors


class ActionFactoryAction(BaseAction):
    """
    Dynamically creates and runs another Action at runtime using a factory function.

    This is useful for generating context-specific behavior (e.g., dynamic HTTPActions)
    where the structure of the next action depends on runtime values.

    Args:
        name (str): Name of the action.
        factory (Callable): A function that returns a BaseAction given args/kwargs.
        inject_last_result (bool): Whether to inject last_result into the factory.
        inject_into (str): The name of the kwarg to inject last_result as.
    """

    def __init__(
        self,
        name: str,
        factory: ActionFactoryProtocol,
        *,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        preview_args: tuple[Any, ...] = (),
        preview_kwargs: dict[str, Any] = {},
    ):
        super().__init__(
            name=name,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
        )
        self.factory = factory
        self.preview_args = preview_args
        self.preview_kwargs = preview_kwargs

    async def _run(self, *args, **kwargs) -> Any:
        updated_kwargs = self._maybe_inject_last_result(kwargs)
        context = ExecutionContext(
            name=f"{self.name} (factory)",
            args=args,
            kwargs=updated_kwargs,
            action=self,
        )
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            generated_action = self.factory(*args, **updated_kwargs)
            if not isinstance(generated_action, BaseAction):
                raise TypeError(
                    f"[{self.name}] Factory must return a BaseAction, got {type(generated_action).__name__}"
                )
            if self.shared_context:
                generated_action.set_shared_context(self.shared_context)
            if self.options_manager:
                generated_action.set_options_manager(self.options_manager)
            context.result = await generated_action(*args, **kwargs)
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return context.result
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            raise
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    async def preview(self, parent: Tree | None = None):
        label = f"[{OneColors.CYAN_b}]🏗️ ActionFactory[/] '{self.name}'"
        tree = parent.add(label) if parent else Tree(label)

        try:
            generated = self.factory(*self.preview_args, **self.preview_kwargs)
            if isinstance(generated, BaseAction):
                await generated.preview(parent=tree)
            else:
                tree.add(
                    f"[{OneColors.DARK_RED}]⚠️ Factory did not return a BaseAction[/]"
                )
        except Exception as error:
            tree.add(f"[{OneColors.DARK_RED}]⚠️ Preview failed: {error}[/]")

        if not parent:
            self.console.print(tree)
