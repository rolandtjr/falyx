"""command.py
Any Action or Command is callable and supports the signature:
    result = thing(*args, **kwargs)

This guarantees:
- Hook lifecycle (before/after/error/teardown)
- Timing
- Consistent return values
"""
from __future__ import annotations

from typing import Any, Callable

from prompt_toolkit.formatted_text import FormattedText
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from rich.console import Console
from rich.tree import Tree

from falyx.action import Action, BaseAction
from falyx.context import ExecutionContext
from falyx.debug import register_debug_hooks
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.retry import RetryPolicy
from falyx.themes.colors import OneColors
from falyx.utils import _noop, ensure_async, logger

console = Console()


class Command(BaseModel):
    """Class representing an command in the menu."""
    key: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    action: BaseAction | Callable[[], Any] = _noop
    args: tuple = ()
    kwargs: dict[str, Any] = Field(default_factory=dict)
    help_text: str = ""
    color: str = OneColors.WHITE
    confirm: bool = False
    confirm_message: str = "Are you sure?"
    preview_before_confirm: bool = True
    spinner: bool = False
    spinner_message: str = "Processing..."
    spinner_type: str = "dots"
    spinner_style: str = OneColors.CYAN
    spinner_kwargs: dict[str, Any] = Field(default_factory=dict)
    hooks: "HookManager" = Field(default_factory=HookManager)
    retry: bool = False
    retry_all: bool = False
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    tags: list[str] = Field(default_factory=list)
    logging_hooks: bool = False

    _context: ExecutionContext | None = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization to set up the action and hooks."""
        if self.retry and isinstance(self.action, Action):
            self.action.enable_retry()
        elif self.retry_policy and isinstance(self.action, Action):
            self.action.set_retry_policy(self.retry_policy)
        elif self.retry:
            logger.warning(f"[Command:{self.key}] Retry requested, but action is not an Action instance.")
        if self.retry_all:
            self.action.enable_retries_recursively(self.action, self.retry_policy)

        if self.logging_hooks and isinstance(self.action, BaseAction):
            register_debug_hooks(self.action.hooks)

    @field_validator("action", mode="before")
    @classmethod
    def wrap_callable_as_async(cls, action: Any) -> Any:
        if isinstance(action, BaseAction):
            return action
        elif callable(action):
            return ensure_async(action)
        raise TypeError("Action must be a callable or an instance of BaseAction")

    def __str__(self):
        return f"Command(key='{self.key}', description='{self.description}')"

    async def __call__(self, *args, **kwargs):
        """Run the action with full hook lifecycle, timing, and error handling."""
        combined_args = args + self.args
        combined_kwargs = {**self.kwargs, **kwargs}
        context = ExecutionContext(
            name=self.description,
            args=combined_args,
            kwargs=combined_kwargs,
            action=self,
        )
        self._context = context
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
                logger.info(f"✅ Recovered: {self.key}")
                return context.result
            raise error
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
            er.record(context)

    @property
    def result(self) -> Any:
        """Get the result of the action."""
        return self._context.result if self._context else None

    @property
    def confirmation_prompt(self) -> FormattedText:
        """Generate a styled prompt_toolkit FormattedText confirmation message."""
        if self.confirm_message and self.confirm_message != "Are you sure?":
            return FormattedText([
                ("class:confirm", self.confirm_message)
            ])

        action_name = getattr(self.action, "__name__", None)
        if isinstance(self.action, BaseAction):
            action_name = self.action.name

        prompt = [(OneColors.WHITE, "Confirm execution of ")]

        prompt.append((OneColors.BLUE_b, f"{self.key}"))
        prompt.append((OneColors.BLUE_b, f" — {self.description} "))

        if action_name:
            prompt.append(("class:confirm", f"(calls `{action_name}`) "))

        if self.args or self.kwargs:
            prompt.append((OneColors.DARK_YELLOW, f"with args={self.args}, kwargs={self.kwargs} "))

        return FormattedText(prompt)

    def log_summary(self):
        if self._context:
            self._context.log_summary()

    async def preview(self):
        label = f"[{OneColors.GREEN_b}]Command:[/] '{self.key}' — {self.description}"

        if hasattr(self.action, "preview") and callable(self.action.preview):
            tree = Tree(label)
            await self.action.preview(parent=tree)
            console.print(tree)
        elif callable(self.action):
            console.print(f"{label}")
            console.print(
                f"[{OneColors.LIGHT_RED_b}]→ Would call:[/] {self.action.__name__} "
                f"[dim](args={self.args}, kwargs={self.kwargs})[/dim]"
            )
        else:
            console.print(f"{label}")
            console.print(f"[{OneColors.DARK_RED}]⚠️ Action is not callable or lacks a preview method.[/]")
