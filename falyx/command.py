# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""command.py

Defines the Command class for Falyx CLI.

Commands are callable units representing a menu option or CLI task,
wrapping either a BaseAction or a simple function. They provide:

- Hook lifecycle (before, on_success, on_error, after, on_teardown)
- Execution timing and duration tracking
- Retry logic (single action or recursively through action trees)
- Confirmation prompts and spinner integration
- Result capturing and summary logging
- Rich-based preview for CLI display

Every Command is self-contained, configurable, and plays a critical role
in building robust interactive menus.
"""
from __future__ import annotations

from functools import cached_property
from typing import Any, Callable

from prompt_toolkit.formatted_text import FormattedText
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from rich.console import Console
from rich.tree import Tree

from falyx.action import Action, ActionGroup, BaseAction, ChainedAction
from falyx.context import ExecutionContext
from falyx.debug import register_debug_hooks
from falyx.exceptions import FalyxError
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.io_action import BaseIOAction
from falyx.options_manager import OptionsManager
from falyx.prompt_utils import should_prompt_user
from falyx.retry import RetryPolicy
from falyx.retry_utils import enable_retries_recursively
from falyx.themes.colors import OneColors
from falyx.utils import _noop, confirm_async, ensure_async, logger

console = Console(color_system="auto")


class Command(BaseModel):
    """
    Represents a selectable command in a Falyx menu system.

    A Command wraps an executable action (function, coroutine, or BaseAction)
    and enhances it with:

    - Lifecycle hooks (before, success, error, after, teardown)
    - Retry support (single action or recursive for chained/grouped actions)
    - Confirmation prompts for safe execution
    - Spinner visuals during execution
    - Tagging for categorization and filtering
    - Rich-based CLI previews
    - Result tracking and summary reporting

    Commands are built to be flexible yet robust, enabling dynamic CLI workflows
    without sacrificing control or reliability.

    Attributes:
        key (str): Primary trigger key for the command.
        description (str): Short description for the menu display.
        hidden (bool): Toggles visibility in the menu.
        aliases (list[str]): Alternate keys or phrases.
        action (BaseAction | Callable): The executable logic.
        args (tuple): Static positional arguments.
        kwargs (dict): Static keyword arguments.
        help_text (str): Additional help or guidance text.
        style (str): Rich style for description.
        confirm (bool): Whether to require confirmation before executing.
        confirm_message (str): Custom confirmation prompt.
        preview_before_confirm (bool): Whether to preview before confirming.
        spinner (bool): Whether to show a spinner during execution.
        spinner_message (str): Spinner text message.
        spinner_type (str): Spinner style (e.g., dots, line, etc.).
        spinner_style (str): Color or style of the spinner.
        spinner_kwargs (dict): Extra spinner configuration.
        hooks (HookManager): Hook manager for lifecycle events.
        retry (bool): Enable retry on failure.
        retry_all (bool): Enable retry across chained or grouped actions.
        retry_policy (RetryPolicy): Retry behavior configuration.
        tags (list[str]): Organizational tags for the command.
        logging_hooks (bool): Whether to attach logging hooks automatically.
        requires_input (bool | None): Indicates if the action needs input.

    Methods:
        __call__(): Executes the command, respecting hooks and retries.
        preview(): Rich tree preview of the command.
        confirmation_prompt(): Formatted prompt for confirmation.
        result: Property exposing the last result.
        log_summary(): Summarizes execution details to the console.
    """

    key: str
    description: str
    action: BaseAction | Callable[[], Any] = _noop
    args: tuple = ()
    kwargs: dict[str, Any] = Field(default_factory=dict)
    hidden: bool = False
    aliases: list[str] = Field(default_factory=list)
    help_text: str = ""
    style: str = OneColors.WHITE
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
    requires_input: bool | None = None
    options_manager: OptionsManager = Field(default_factory=OptionsManager)

    _context: ExecutionContext | None = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @field_validator("action", mode="before")
    @classmethod
    def wrap_callable_as_async(cls, action: Any) -> Any:
        if isinstance(action, BaseAction):
            return action
        elif callable(action):
            return ensure_async(action)
        raise TypeError("Action must be a callable or an instance of BaseAction")

    def model_post_init(self, __context: Any) -> None:
        """Post-initialization to set up the action and hooks."""
        if self.retry and isinstance(self.action, Action):
            self.action.enable_retry()
        elif self.retry_policy and isinstance(self.action, Action):
            self.action.set_retry_policy(self.retry_policy)
        elif self.retry:
            logger.warning(
                f"[Command:{self.key}] Retry requested, but action is not an Action instance."
            )
        if self.retry_all and isinstance(self.action, BaseAction):
            self.retry_policy.enabled = True
            enable_retries_recursively(self.action, self.retry_policy)
        elif self.retry_all:
            logger.warning(
                f"[Command:{self.key}] Retry all requested, but action is not a BaseAction instance."
            )

        if self.logging_hooks and isinstance(self.action, BaseAction):
            register_debug_hooks(self.action.hooks)

        if self.requires_input is None and self.detect_requires_input:
            self.requires_input = True
            self.hidden = True
        elif self.requires_input is None:
            self.requires_input = False

    @cached_property
    def detect_requires_input(self) -> bool:
        """Detect if the action requires input based on its type."""
        if isinstance(self.action, BaseIOAction):
            return True
        elif isinstance(self.action, ChainedAction):
            return (
                isinstance(self.action.actions[0], BaseIOAction)
                if self.action.actions
                else False
            )
        elif isinstance(self.action, ActionGroup):
            return any(isinstance(action, BaseIOAction) for action in self.action.actions)
        return False

    def _inject_options_manager(self) -> None:
        """Inject the options manager into the action if applicable."""
        if isinstance(self.action, BaseAction):
            self.action.set_options_manager(self.options_manager)

    async def __call__(self, *args, **kwargs) -> Any:
        """
        Run the action with full hook lifecycle, timing, error handling,
        confirmation prompts, preview, and spinner integration.
        """
        self._inject_options_manager()
        combined_args = args + self.args
        combined_kwargs = {**self.kwargs, **kwargs}
        context = ExecutionContext(
            name=self.description,
            args=combined_args,
            kwargs=combined_kwargs,
            action=self,
        )
        self._context = context

        if should_prompt_user(confirm=self.confirm, options=self.options_manager):
            if self.preview_before_confirm:
                await self.preview()
            if not await confirm_async(self.confirmation_prompt):
                logger.info(f"[Command:{self.key}] ❌ Cancelled by user.")
                raise FalyxError(f"[Command:{self.key}] Cancelled by confirmation.")

        context.start_timer()

        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            if self.spinner:
                with console.status(
                    self.spinner_message,
                    spinner=self.spinner_type,
                    spinner_style=self.spinner_style,
                    **self.spinner_kwargs,
                ):
                    result = await self.action(*combined_args, **combined_kwargs)
            else:
                result = await self.action(*combined_args, **combined_kwargs)

            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            return context.result
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
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
            return FormattedText([("class:confirm", self.confirm_message)])

        action_name = getattr(self.action, "__name__", None)
        if isinstance(self.action, BaseAction):
            action_name = self.action.name

        prompt = [(OneColors.WHITE, "Confirm execution of ")]

        prompt.append((OneColors.BLUE_b, f"{self.key}"))
        prompt.append((OneColors.BLUE_b, f" — {self.description} "))

        if action_name:
            prompt.append(("class:confirm", f"(calls `{action_name}`) "))

        if self.args or self.kwargs:
            prompt.append(
                (OneColors.DARK_YELLOW, f"with args={self.args}, kwargs={self.kwargs} ")
            )

        return FormattedText(prompt)

    def log_summary(self) -> None:
        if self._context:
            self._context.log_summary()

    async def preview(self) -> None:
        label = f"[{OneColors.GREEN_b}]Command:[/] '{self.key}' — {self.description}"

        if hasattr(self.action, "preview") and callable(self.action.preview):
            tree = Tree(label)
            await self.action.preview(parent=tree)
            if self.help_text:
                tree.add(f"[dim]💡 {self.help_text}[/dim]")
            console.print(tree)
        elif callable(self.action) and not isinstance(self.action, BaseAction):
            console.print(f"{label}")
            if self.help_text:
                console.print(f"[dim]💡 {self.help_text}[/dim]")
            console.print(
                f"[{OneColors.LIGHT_RED_b}]→ Would call:[/] {self.action.__name__}"
                f"[dim](args={self.args}, kwargs={self.kwargs})[/dim]"
            )
        else:
            console.print(f"{label}")
            if self.help_text:
                console.print(f"[dim]💡 {self.help_text}[/dim]")
            console.print(
                f"[{OneColors.DARK_RED}]⚠️ Action is not callable or lacks a preview method.[/]"
            )

    def __str__(self) -> str:
        return (
            f"Command(key='{self.key}', description='{self.description}' "
            f"action='{self.action}')"
        )
