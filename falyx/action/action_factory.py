# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines `ActionFactory`, a dynamic Falyx Action that defers the construction of its
underlying logic to runtime using a user-defined factory function.

This pattern is useful when the specific Action to execute cannot be determined until
execution time—such as when branching on data, generating parameterized HTTP requests,
or selecting configuration-aware flows. `ActionFactory` integrates seamlessly with the
Falyx lifecycle system and supports hook propagation, teardown registration, and
contextual previewing.

Key Features:
- Accepts a factory function that returns a `BaseAction` instance
- Supports injection of `last_result` and arbitrary args/kwargs
- Integrates into chained or standalone workflows
- Automatically previews generated action tree
- Propagates shared context and teardown hooks to the returned action

Common Use Cases:
- Conditional or data-driven action generation
- Configurable workflows with dynamic behavior
- Adapter for factory-style dependency injection in CLI flows

Example:
    def generate_request_action(env):
        return HTTPAction(f"GET /status/{env}", url=f"https://api/{env}/status")

    ActionFactory(
        name="GetEnvStatus",
        factory=generate_request_action,
        inject_last_result=True,
    )
"""
from typing import Any, Callable

from rich.tree import Tree

from falyx.action.base_action import BaseAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.logger import logger
from falyx.protocols import ActionFactoryProtocol
from falyx.themes import OneColors
from falyx.utils import ensure_async


class ActionFactory(BaseAction):
    """
    Dynamically creates and runs another Action at runtime using a factory function.

    This is useful for generating context-specific behavior (e.g., dynamic HTTPActions)
    where the structure of the next action depends on runtime values.

    Args:
        name (str): Name of the action. Used for logging and debugging.
        factory (Callable): A function that returns a BaseAction given args/kwargs.
        inject_last_result (bool): Whether to inject last_result into the factory.
        inject_into (str): The name of the kwarg to inject last_result as.
        args (tuple, optional): Positional arguments for the factory.
        kwargs (dict, optional): Keyword arguments for the factory.
        preview_args (tuple, optional): Positional arguments for the preview.
        preview_kwargs (dict, optional): Keyword arguments for the preview.
    """

    def __init__(
        self,
        name: str,
        factory: ActionFactoryProtocol,
        *,
        inject_last_result: bool = False,
        inject_into: str = "last_result",
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        preview_args: tuple[Any, ...] = (),
        preview_kwargs: dict[str, Any] | None = None,
    ):
        super().__init__(
            name=name,
            inject_last_result=inject_last_result,
            inject_into=inject_into,
        )
        self.factory = factory
        self.args = args
        self.kwargs = kwargs or {}
        self.preview_args = preview_args
        self.preview_kwargs = preview_kwargs or {}

    @property
    def factory(self) -> ActionFactoryProtocol:
        return self._factory  # type: ignore[return-value]

    @factory.setter
    def factory(self, value: ActionFactoryProtocol):
        self._factory = ensure_async(value)

    def get_infer_target(self) -> tuple[Callable[..., Any], None]:
        return self.factory, None

    async def _run(self, *args, **kwargs) -> Any:
        args = (*self.args, *args)
        kwargs = {**self.kwargs, **kwargs}
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
            generated_action = await self.factory(*args, **updated_kwargs)
            if not isinstance(generated_action, BaseAction):
                raise TypeError(
                    f"[{self.name}] Factory must return a BaseAction, got "
                    f"{type(generated_action).__name__}"
                )
            if self.shared_context:
                generated_action.set_shared_context(self.shared_context)
                if hasattr(generated_action, "register_teardown") and callable(
                    generated_action.register_teardown
                ):
                    generated_action.register_teardown(self.shared_context.action.hooks)
                    logger.debug(
                        "[%s] Registered teardown for %s",
                        self.name,
                        generated_action.name,
                    )
            if self.options_manager:
                generated_action.set_options_manager(self.options_manager)
            context.result = await generated_action()
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
            generated = None
            if self.args or self.kwargs:
                try:
                    generated = await self.factory(*self.args, **self.kwargs)
                except TypeError:
                    ...

            if not generated:
                generated = await self.factory(*self.preview_args, **self.preview_kwargs)

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

    def __str__(self) -> str:
        return (
            f"ActionFactory(name={self.name!r}, "
            f"inject_last_result={self.inject_last_result}, "
            f"factory={self._factory.__name__ if hasattr(self._factory, '__name__') else type(self._factory).__name__}, "
            f"args={self.args!r}, kwargs={self.kwargs!r})"
        )
