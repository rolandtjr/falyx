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

import shlex
from typing import Any, Awaitable, Callable

from prompt_toolkit.formatted_text import FormattedText
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from rich.tree import Tree

from falyx.action.action import Action
from falyx.action.base_action import BaseAction
from falyx.console import console
from falyx.context import ExecutionContext
from falyx.debug import register_debug_hooks
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.logger import logger
from falyx.options_manager import OptionsManager
from falyx.parser.command_argument_parser import CommandArgumentParser
from falyx.parser.signature import infer_args_from_func
from falyx.prompt_utils import confirm_async, should_prompt_user
from falyx.protocols import ArgParserProtocol
from falyx.retry import RetryPolicy
from falyx.retry_utils import enable_retries_recursively
from falyx.signals import CancelSignal
from falyx.themes import OneColors
from falyx.utils import ensure_async


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
        options_manager (OptionsManager): Manages global command-line options.
        arg_parser (CommandArgumentParser): Parses command arguments.
        arguments (list[dict[str, Any]]): Argument definitions for the command.
        argument_config (Callable[[CommandArgumentParser], None] | None): Function to configure arguments
            for the command parser.
        arg_metadata (dict[str, str | dict[str, Any]]): Metadata for arguments,
            such as help text or choices.
        simple_help_signature (bool): Whether to use a simplified help signature.
        custom_parser (ArgParserProtocol | None): Custom argument parser.
        custom_help (Callable[[], str | None] | None): Custom help message generator.
        auto_args (bool): Automatically infer arguments from the action.

    Methods:
        __call__(): Executes the command, respecting hooks and retries.
        preview(): Rich tree preview of the command.
        confirmation_prompt(): Formatted prompt for confirmation.
        result: Property exposing the last result.
        log_summary(): Summarizes execution details to the console.
    """

    key: str
    description: str
    action: BaseAction | Callable[..., Any] | Callable[..., Awaitable[Any]]
    args: tuple = ()
    kwargs: dict[str, Any] = Field(default_factory=dict)
    hidden: bool = False
    aliases: list[str] = Field(default_factory=list)
    help_text: str = ""
    help_epilog: str = ""
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
    options_manager: OptionsManager = Field(default_factory=OptionsManager)
    arg_parser: CommandArgumentParser | None = None
    arguments: list[dict[str, Any]] = Field(default_factory=list)
    argument_config: Callable[[CommandArgumentParser], None] | None = None
    custom_parser: ArgParserProtocol | None = None
    custom_help: Callable[[], str | None] | None = None
    auto_args: bool = True
    arg_metadata: dict[str, str | dict[str, Any]] = Field(default_factory=dict)
    simple_help_signature: bool = False

    _context: ExecutionContext | None = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def parse_args(
        self, raw_args: list[str] | str, from_validate: bool = False
    ) -> tuple[tuple, dict]:
        if callable(self.custom_parser):
            if isinstance(raw_args, str):
                try:
                    raw_args = shlex.split(raw_args)
                except ValueError:
                    logger.warning(
                        "[Command:%s] Failed to split arguments: %s",
                        self.key,
                        raw_args,
                    )
                    return ((), {})
            return self.custom_parser(raw_args)

        if isinstance(raw_args, str):
            try:
                raw_args = shlex.split(raw_args)
            except ValueError:
                logger.warning(
                    "[Command:%s] Failed to split arguments: %s",
                    self.key,
                    raw_args,
                )
                return ((), {})
        if not isinstance(self.arg_parser, CommandArgumentParser):
            logger.warning(
                "[Command:%s] No argument parser configured, using default parsing.",
                self.key,
            )
            return ((), {})
        return await self.arg_parser.parse_args_split(
            raw_args, from_validate=from_validate
        )

    @field_validator("action", mode="before")
    @classmethod
    def wrap_callable_as_async(cls, action: Any) -> Any:
        if isinstance(action, BaseAction):
            return action
        elif callable(action):
            return ensure_async(action)
        raise TypeError("Action must be a callable or an instance of BaseAction")

    def get_argument_definitions(self) -> list[dict[str, Any]]:
        if self.arguments:
            return self.arguments
        elif callable(self.argument_config) and isinstance(
            self.arg_parser, CommandArgumentParser
        ):
            self.argument_config(self.arg_parser)
        elif self.auto_args:
            if isinstance(self.action, BaseAction):
                infer_target, maybe_metadata = self.action.get_infer_target()
                # merge metadata with the action's metadata if not already in self.arg_metadata
                if maybe_metadata:
                    self.arg_metadata = {**maybe_metadata, **self.arg_metadata}
                return infer_args_from_func(infer_target, self.arg_metadata)
            elif callable(self.action):
                return infer_args_from_func(self.action, self.arg_metadata)
        return []

    def model_post_init(self, _: Any) -> None:
        """Post-initialization to set up the action and hooks."""
        if self.retry and isinstance(self.action, Action):
            self.action.enable_retry()
        elif self.retry_policy and isinstance(self.action, Action):
            self.action.set_retry_policy(self.retry_policy)
        elif self.retry:
            logger.warning(
                "[Command:%s] Retry requested, but action is not an Action instance.",
                self.key,
            )
        if self.retry_all and isinstance(self.action, BaseAction):
            self.retry_policy.enabled = True
            enable_retries_recursively(self.action, self.retry_policy)
        elif self.retry_all:
            logger.warning(
                "[Command:%s] Retry all requested, but action is not a BaseAction.",
                self.key,
            )

        if self.logging_hooks and isinstance(self.action, BaseAction):
            register_debug_hooks(self.action.hooks)

        if self.arg_parser is None and not self.custom_parser:
            self.arg_parser = CommandArgumentParser(
                command_key=self.key,
                command_description=self.description,
                command_style=self.style,
                help_text=self.help_text,
                help_epilog=self.help_epilog,
                aliases=self.aliases,
            )
            for arg_def in self.get_argument_definitions():
                self.arg_parser.add_argument(*arg_def.pop("flags"), **arg_def)

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
                logger.info("[Command:%s] Cancelled by user.", self.key)
                raise CancelSignal(f"[Command:{self.key}] Cancelled by confirmation.")

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

    @property
    def usage(self) -> str:
        """Generate a help string for the command arguments."""
        if not self.arg_parser:
            return "No arguments defined."

        command_keys_text = self.arg_parser.get_command_keys_text(plain_text=True)
        options_text = self.arg_parser.get_options_text(plain_text=True)
        return f"  {command_keys_text:<20}  {options_text} "

    @property
    def help_signature(self) -> str:
        """Generate a help signature for the command."""
        if self.arg_parser and not self.simple_help_signature:
            signature = [self.arg_parser.get_usage()]
            signature.append(f"  {self.help_text or self.description}")
            if self.tags:
                signature.append(f"  [dim]Tags: {', '.join(self.tags)}[/dim]")
            return "\n".join(signature).strip()

        command_keys = " | ".join(
            [f"[{self.style}]{self.key}[/{self.style}]"]
            + [f"[{self.style}]{alias}[/{self.style}]" for alias in self.aliases]
        )
        return f"{command_keys}  {self.description}"

    def log_summary(self) -> None:
        if self._context:
            self._context.log_summary()

    def show_help(self) -> bool:
        """Display the help message for the command."""
        if callable(self.custom_help):
            output = self.custom_help()
            if output:
                console.print(output)
            return True
        if isinstance(self.arg_parser, CommandArgumentParser):
            self.arg_parser.render_help()
            return True
        return False

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
                f"[{OneColors.DARK_RED}]⚠️ No preview available for this action.[/]"
            )

    def __str__(self) -> str:
        return (
            f"Command(key='{self.key}', description='{self.description}' "
            f"action='{self.action}')"
        )
