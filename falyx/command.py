# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""Command abstraction for the Falyx CLI framework.

This module defines the `Command` class, which represents a single executable
unit exposed to users via CLI or interactive menu interfaces.

A `Command` acts as a bridge between:
- User input (parsed via CommandArgumentParser)
- Execution logic (encapsulated in Action / BaseAction)
- Runtime configuration (OptionsManager)
- Lifecycle hooks (HookManager)

Core Responsibilities:
- Define command identity (key, aliases, description)
- Bind an executable action or workflow
- Configure argument parsing via CommandArgumentParser
- Separate execution arguments (e.g. retries, confirm) from action arguments
- Manage lifecycle hooks for command-level execution
- Provide help, usage, and preview interfaces
- Execution timing and duration tracking
- Confirmation prompts and spinner integration

Execution Model:
1. CLI input is routed via FalyxParser into a resolved Command
2. Arguments are parsed via CommandArgumentParser
3. Parsed values are split into:
   - positional args
   - keyword args
   - execution args (e.g. retries, summary)
4. Execution occurs via the bound Action with lifecycle hooks applied
5. Results and context are tracked via ExecutionContext / ExecutionRegistry

Key Concepts:
- Commands are *user-facing entrypoints*, not execution units themselves
- Execution is always delegated to an underlying Action or callable
- Argument parsing is declarative and optional
- Execution options are handled separately from business logic inputs

This module defines the primary abstraction used by Falyx to expose structured,
composable workflows as CLI commands.
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
from falyx.context import ExecutionContext, InvocationContext
from falyx.debug import register_debug_hooks
from falyx.exceptions import CommandArgumentError, NotAFalyxError
from falyx.execution_option import ExecutionOption
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.hooks import spinner_before_hook, spinner_teardown_hook
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
    """Represents a user-invokable command in Falyx.

    A `Command` encapsulates all metadata, parsing logic, and execution behavior
    required to expose a callable workflow through the Falyx CLI or interactive
    menu system.

    It is responsible for:
    - Identifying the command via key and aliases
    - Binding an executable Action or callable
    - Parsing user-provided arguments
    - Managing execution configuration (retries, confirmation, etc.)
    - Integrating with lifecycle hooks and execution context

    Architecture:
    - Parsing is delegated to CommandArgumentParser
    - Execution is delegated to BaseAction / Action
    - Runtime configuration is managed via OptionsManager
    - Lifecycle hooks are managed via HookManager

    Argument Handling:
    - Supports positional and keyword arguments via CommandArgumentParser
    - Separates execution-specific options (e.g. retries, confirm flags)
      from action arguments
    - Returns structured `(args, kwargs, execution_args)` for execution

    Execution Behavior:
    - Callable via `await command(*args, **kwargs)`
    - Applies lifecycle hooks:
        before → on_success/on_error → after → on_teardown
    - Supports preview mode for dry-run introspection
    - Supports retry policies and confirmation flows
    - Result tracking and summary reporting

    Help & Introspection:
    - Provides usage, help text, and TLDR examples
    - Supports both CLI help and interactive menu rendering
    - Can expose simplified or full help signatures

    Args:
        key (str): Primary identifier used to invoke the command.
        description (str): Short description for the menu display.
        action (BaseAction | Callable[..., Any]):
            Execution logic for the command.
        args (tuple, optional): Static positional arguments.
        kwargs (dict[str, Any], optional): Static keyword arguments.
        hidden (bool): Whether to hide the command from menus.
        aliases (list[str], optional): Alternate names for invocation.
        help_text (str): Help description shown in CLI/menu.
        help_epilog (str): Additional help content.
        style (str): Rich style used for rendering.
        confirm (bool): Whether confirmation is required before execution.
        confirm_message (str): Confirmation prompt text.
        preview_before_confirm (bool): Whether to preview before confirmation.
        spinner (bool): Enable spinner during execution.
        spinner_message (str): Spinner message text.
        spinner_type (str): Rich Spinner animation type (e.g., dots, line, etc.).
        spinner_style (str): Rich style for the spinner.
        spinner_speed (float): Spinner speed multiplier.
        hooks (HookManager | None): Hook manager for lifecycle events.
        tags (list[str], optional): Tags for grouping and filtering.
        logging_hooks (bool): Enable debug logging hooks.
        retry (bool): Enable retry behavior.
        retry_all (bool): Apply retry to all nested actions.
        retry_policy (RetryPolicy | None): Retry configuration.
        arg_parser (CommandArgumentParser | None):
            Custom argument parser instance.
        execution_options (frozenset[ExecutionOption], optional):
            Enabled execution-level options.
        arguments (list[dict[str, Any]], optional):
            Declarative argument definitions.
        argument_config (Callable[[CommandArgumentParser], None] | None):
            Callback to configure parser.
        custom_parser (ArgParserProtocol | None):
            Override parser logic entirely.
        custom_help (Callable[[], str | None] | None):
            Override help rendering.
        custom_tldr (Callable[[], str | None] | None):
            Override TLDR rendering.
        auto_args (bool): Auto-generate arguments from action signature.
        arg_metadata (dict[str, Any], optional): Metadata for arguments.
        simple_help_signature (bool): Use simplified help formatting.
        ignore_in_history (bool):
            Ignore command for `last_result` in execution history.
        options_manager (OptionsManager | None):
            Shared options manager instance.
        program (str | None): The parent program name.

    Raises:
        CommandArgumentError: If argument parsing fails.
        InvalidActionError: If action is not callable or invalid.
        FalyxError: If command configuration is invalid.

    Notes:
        - Commands are lightweight wrappers; execution logic belongs in Actions
        - Argument parsing and execution are intentionally decoupled
        - Commands are case-insensitive and support alias resolution
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
    spinner_speed: float = 1.0
    hooks: "HookManager" = Field(default_factory=HookManager)
    retry: bool = False
    retry_all: bool = False
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    tags: list[str] = Field(default_factory=list)
    logging_hooks: bool = False
    options_manager: OptionsManager = Field(default_factory=OptionsManager)
    arg_parser: CommandArgumentParser | None = None
    execution_options: frozenset[ExecutionOption] = Field(default_factory=frozenset)
    arguments: list[dict[str, Any]] = Field(default_factory=list)
    argument_config: Callable[[CommandArgumentParser], None] | None = None
    custom_parser: ArgParserProtocol | None = None
    custom_help: Callable[[], None] | None = None
    custom_tldr: Callable[[], None] | None = None
    auto_args: bool = True
    arg_metadata: dict[str, str | dict[str, Any]] = Field(default_factory=dict)
    simple_help_signature: bool = False
    ignore_in_history: bool = False
    program: str | None = None

    _context: ExecutionContext | None = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    async def resolve_args(
        self,
        raw_args: list[str] | str,
        from_validate: bool = False,
        invocation_context: InvocationContext | None = None,
    ) -> tuple[tuple, dict, dict]:
        """Parse CLI arguments into execution-ready components.

        This method delegates argument parsing to the configured
        CommandArgumentParser (if present) and normalizes the result into three
        distinct groups used during execution:

        - positional arguments (`args`)
        - keyword arguments (`kwargs`)
        - execution arguments (`execution_args`)

        Execution arguments represent runtime configuration (e.g. retries,
        confirmation flags, summary output) and are handled separately from the
        action's business logic inputs.

        Behavior:
        - If an argument parser is defined, uses `CommandArgumentParser.parse_args_split()`
        to resolve and type-coerce all inputs.
        - If no parser is defined, returns empty args and kwargs.
        - Supports validation mode (`from_validate=True`) for interactive input,
        deferring certain errors and resolver execution where applicable.
        - Handles help/preview signals raised during parsing.

        Args:
            args (list[str] | str | None): CLI-style argument tokens or a single string.
            from_validate (bool): Whether parsing is occurring in validation mode
                (e.g. prompt_toolkit validator). When True, may suppress eager
                resolution or defer certain errors.

        Returns:
            tuple:
                - tuple[Any, ...]: Positional arguments for execution.
                - dict[str, Any]: Keyword arguments for execution.
                - dict[str, Any]: Execution-specific arguments (e.g. retries,
                confirm flags, summary).

        Raises:
            CommandArgumentError: If argument parsing or validation fails.
            HelpSignal: If help or TLDR output is triggered during parsing.

        Notes:
            - Execution arguments are not passed to the underlying Action.
            - This method is the canonical boundary between CLI parsing and
            execution semantics.
        """
        if self.custom_parser is not None:
            if not callable(self.custom_parser):
                raise NotAFalyxError(
                    "custom_parser must be a callable that implements ArgParserProtocol."
                )
            if isinstance(raw_args, str):
                try:
                    raw_args = shlex.split(raw_args)
                except ValueError as error:
                    raise CommandArgumentError(
                        f"[{self.key}] Failed to parse arguments: {error}"
                    ) from error
            return self.custom_parser(raw_args)

        if isinstance(raw_args, str):
            try:
                raw_args = shlex.split(raw_args)
            except ValueError as error:
                raise CommandArgumentError(
                    f"[{self.key}] Failed to parse arguments: {error}"
                ) from error

        if self.arg_parser is None:
            raise NotAFalyxError(
                "Command has no parser configured. "
                "Provide a custom_parser or CommandArgumentParser."
            )
        if not isinstance(self.arg_parser, CommandArgumentParser):
            raise NotAFalyxError(
                "arg_parser must be an instance of CommandArgumentParser"
            )

        return await self.arg_parser.parse_args_split(
            raw_args,
            from_validate=from_validate,
            invocation_context=invocation_context,
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
                program=self.program,
                options_manager=self.options_manager,
            )
            for arg_def in self.get_argument_definitions():
                self.arg_parser.add_argument(*arg_def.pop("flags"), **arg_def)

        if isinstance(self.arg_parser, CommandArgumentParser) and self.execution_options:
            self.arg_parser.enable_execution_options(self.execution_options)

        if isinstance(self.arg_parser, CommandArgumentParser):
            self.arg_parser.set_options_manager(self.options_manager)

        if self.ignore_in_history and isinstance(self.action, BaseAction):
            self.action.ignore_in_history = True

    def _inject_options_manager(self) -> None:
        """Inject the options manager into the action if applicable."""
        if isinstance(self.action, BaseAction):
            self.action.set_options_manager(self.options_manager)

    async def __call__(self, *args, **kwargs) -> Any:
        """Execute the command's underlying action with lifecycle management.

        This method invokes the bound action (BaseAction or callable) using the
        provided arguments while applying the full Falyx execution lifecycle.

        Execution Flow:
        1. Create an ExecutionContext for tracking inputs, results, and timing
        2. Trigger `before` hooks
        3. Execute the underlying action
        4. Trigger `on_success` or `on_error` hooks
        5. Trigger `after` and `on_teardown` hooks
        6. Record execution via ExecutionRegistry

        Behavior:
        - Supports both synchronous and asynchronous actions
        - Applies retry policies if configured
        - Integrates with confirmation and execution options via OptionsManager
        - Propagates exceptions unless recovered by hooks (e.g. retry handlers)

        Args:
            *args (Any): Positional arguments passed to the action.
            **kwargs (Any): Keyword arguments passed to the action.

        Returns:
            Any: Result returned by the underlying action.

        Raises:
            Exception: Propagates execution errors unless handled by hooks.

        Notes:
            - This method does not perform argument parsing; inputs are assumed
            to be pre-processed via `resolve_args`.
            - Execution options (e.g. retries, confirm) are applied externally
            via Falyx in OptionsManager before invocation.
            - Lifecycle hooks are always executed, even in failure cases.
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

        command_keys_text = self.arg_parser.get_command_keys_text()
        options_text = self.arg_parser.get_options_text()
        return f"  {command_keys_text:<20}  {options_text} "

    @property
    def help_signature(
        self,
        invocation_context: InvocationContext | None = None,
    ) -> tuple[str, str, str]:
        """Return a formatted help signature for display.

        This property provides the core information used to render command help
        in both CLI and interactive menu modes.

        The signature consists of:
        - usage: A formatted usage string (including arguments if defined)
        - description: A short description of the command
        - tag: Optional tag or category label (if applicable)

        Behavior:
        - If a CommandArgumentParser is present, delegates usage generation to
        the parser (`get_usage()`).
        - Otherwise, constructs a minimal usage string from the command key.
        - Honors `simple_help_signature` to produce a condensed representation
        (e.g. omitting argument details).
        - Applies styling appropriate for Rich rendering.

        Returns:
            tuple:
                - str: Usage string (e.g. "falyx D | deploy [--help] region")
                - str: Command description
                - str: Optional tag/category label

        Notes:
            - This is the primary interface used by help menus, CLI help output,
            and command listings.
            - Formatting may vary depending on CLI vs menu mode.
        """
        if self.arg_parser and not self.simple_help_signature:
            usage = self.arg_parser.get_usage(invocation_context=invocation_context)
            description = f"[dim]{self.help_text or self.description}[/dim]"
            if self.tags:
                tags = f"[dim]Tags: {', '.join(self.tags)}[/dim]"
            else:
                tags = ""
            return usage, description, tags

        command_keys = " | ".join(
            [f"[{self.style}]{self.key}[/{self.style}]"]
            + [f"[{self.style}]{alias}[/{self.style}]" for alias in self.aliases]
        )
        return (
            f"{command_keys}",
            f"[dim]{self.help_text or self.description}[/dim]",
            "",
        )

    def log_summary(self) -> None:
        if self._context:
            self._context.log_summary()

    def render_help(self, invocation_context: InvocationContext | None = None) -> bool:
        """Display the help message for the command."""
        if callable(self.custom_help):
            output = self.custom_help()
            if output:
                console.print(output)
            return True
        if isinstance(self.arg_parser, CommandArgumentParser):
            self.arg_parser.render_help(invocation_context=invocation_context)
            return True
        return False

    def render_tldr(self, invocation_context: InvocationContext | None = None) -> bool:
        """Display the TLDR message for the command."""
        if callable(self.custom_tldr):
            output = self.custom_tldr()
            if output:
                console.print(output)
            return True
        if isinstance(self.arg_parser, CommandArgumentParser):
            self.arg_parser.render_tldr(invocation_context=invocation_context)
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

    @classmethod
    def build(
        cls,
        key: str,
        description: str,
        action: BaseAction | Callable[..., Any],
        *,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        hidden: bool = False,
        aliases: list[str] | None = None,
        help_text: str = "",
        help_epilog: str = "",
        style: str = OneColors.WHITE,
        confirm: bool = False,
        confirm_message: str = "Are you sure?",
        preview_before_confirm: bool = True,
        spinner: bool = False,
        spinner_message: str = "Processing...",
        spinner_type: str = "dots",
        spinner_style: str = OneColors.CYAN,
        spinner_speed: float = 1.0,
        options_manager: OptionsManager | None = None,
        hooks: HookManager | None = None,
        before_hooks: list[Callable] | None = None,
        success_hooks: list[Callable] | None = None,
        error_hooks: list[Callable] | None = None,
        after_hooks: list[Callable] | None = None,
        teardown_hooks: list[Callable] | None = None,
        tags: list[str] | None = None,
        logging_hooks: bool = False,
        retry: bool = False,
        retry_all: bool = False,
        retry_policy: RetryPolicy | None = None,
        arg_parser: CommandArgumentParser | None = None,
        arguments: list[dict[str, Any]] | None = None,
        argument_config: Callable[[CommandArgumentParser], None] | None = None,
        execution_options: list[ExecutionOption | str] | None = None,
        custom_parser: ArgParserProtocol | None = None,
        custom_help: Callable[[], str | None] | None = None,
        custom_tldr: Callable[[], str | None] | None = None,
        auto_args: bool = True,
        arg_metadata: dict[str, str | dict[str, Any]] | None = None,
        simple_help_signature: bool = False,
        ignore_in_history: bool = False,
        program: str | None = None,
    ) -> Command:
        """Build and configure a `Command` instance from high-level constructor inputs.

        This factory centralizes command construction so callers such as `Falyx` and
        `CommandRunner` can create fully configured commands through one consistent
        path. It normalizes optional inputs, validates selected objects, converts
        execution options into their canonical internal form, and registers any
        requested command-level hooks.

        In addition to instantiating the `Command`, this method can:
            - validate and attach an explicit `CommandArgumentParser`
            - normalize execution options into a `frozenset[ExecutionOption]`
            - ensure a shared `OptionsManager` is available
            - attach a custom `HookManager`
            - register lifecycle hooks for the command
            - register spinner hooks when spinner support is enabled

        Args:
            key (str): Primary identifier used to invoke the command.
            description (str): Short description of the command.
            action (BaseAction | Callable[..., Any]): Underlying execution logic for
                the command.
            args (tuple): Static positional arguments applied to every execution.
            kwargs (dict[str, Any] | None): Static keyword arguments applied to every
                execution.
            hidden (bool): Whether the command should be hidden from menu displays.
            aliases (list[str] | None): Optional alternate names for invocation.
            help_text (str): Help text shown in command help output.
            help_epilog (str): Additional help text shown after the main help body.
            style (str): Rich style used when rendering the command.
            confirm (bool): Whether confirmation is required before execution.
            confirm_message (str): Confirmation prompt text.
            preview_before_confirm (bool): Whether to preview before confirmation.
            spinner (bool): Whether to enable spinner lifecycle hooks.
            spinner_message (str): Spinner message text.
            spinner_type (str): Spinner animation type.
            spinner_style (str): Spinner style.
            spinner_speed (float): Spinner speed multiplier.
            options_manager (OptionsManager | None): Shared options manager for the
                command and its parser.
            hooks (HookManager | None): Optional hook manager to assign directly to the
                command.
            before_hooks (list[Callable] | None): Hooks registered for the `BEFORE`
                lifecycle stage.
            success_hooks (list[Callable] | None): Hooks registered for the
                `ON_SUCCESS` lifecycle stage.
            error_hooks (list[Callable] | None): Hooks registered for the `ON_ERROR`
                lifecycle stage.
            after_hooks (list[Callable] | None): Hooks registered for the `AFTER`
                lifecycle stage.
            teardown_hooks (list[Callable] | None): Hooks registered for the
                `ON_TEARDOWN` lifecycle stage.
            tags (list[str] | None): Optional tags used for grouping and filtering.
            logging_hooks (bool): Whether to enable debug hook logging.
            retry (bool): Whether retry behavior is enabled.
            retry_all (bool): Whether retry behavior should be applied recursively.
            retry_policy (RetryPolicy | None): Retry configuration for the command.
            arg_parser (CommandArgumentParser | None): Optional explicit argument
                parser instance.
            arguments (list[dict[str, Any]] | None): Declarative argument
                definitions for the command parser.
            argument_config (Callable[[CommandArgumentParser], None] | None): Callback
                used to configure the argument parser.
            execution_options (list[ExecutionOption | str] | None): Execution-level
                options to enable for the command.
            custom_parser (ArgParserProtocol | None): Optional custom parser
                implementation that overrides normal parser behavior.
            custom_help (Callable[[], str | None] | None): Optional custom help
                renderer.
            custom_tldr (Callable[[], str | None] | None): Optional custom TLDR
                renderer.
            auto_args (bool): Whether to infer arguments automatically from the action
                signature when explicit definitions are not provided.
            arg_metadata (dict[str, str | dict[str, Any]] | None): Optional metadata
                used during argument inference.
            simple_help_signature (bool): Whether to use a simplified help signature.
            ignore_in_history (bool): Whether to exclude the command from execution
                history tracking.
            program (str | None): Parent program name used in help rendering.

        Returns:
            Command: A fully configured `Command` instance.

        Raises:
            NotAFalyxError: If `arg_parser` is provided but is not a
                `CommandArgumentParser` instance, or if `hooks` is provided but is not
                a `HookManager` instance.

        Notes:
            - Execution options supplied as strings are converted to
            `ExecutionOption` enum values before the command is created.
            - If no `options_manager` is provided, a new `OptionsManager` is created.
            - Spinner hooks are registered at build time when `spinner=True`.
            - This method is the canonical command-construction path used by higher-
            level APIs such as `Falyx.add_command()` and `CommandRunner.build()`.
        """
        if arg_parser and not isinstance(arg_parser, CommandArgumentParser):
            raise NotAFalyxError(
                "arg_parser must be an instance of CommandArgumentParser."
            )
        arg_parser = arg_parser

        if options_manager and not isinstance(options_manager, OptionsManager):
            raise NotAFalyxError("options_manager must be an instance of OptionsManager.")
        options_manager = options_manager or OptionsManager()

        if hooks and not isinstance(hooks, HookManager):
            raise NotAFalyxError("hooks must be an instance of HookManager.")
        hooks = hooks or HookManager()

        if retry_policy and not isinstance(retry_policy, RetryPolicy):
            raise NotAFalyxError("retry_policy must be an instance of RetryPolicy.")
        retry_policy = retry_policy or RetryPolicy()

        if execution_options:
            parsed_execution_options = frozenset(
                ExecutionOption(option) if isinstance(option, str) else option
                for option in execution_options
            )
        else:
            parsed_execution_options = frozenset()

        command = Command(
            key=key,
            description=description,
            action=action,
            args=args,
            kwargs=kwargs if kwargs else {},
            hidden=hidden,
            aliases=aliases if aliases else [],
            help_text=help_text,
            help_epilog=help_epilog,
            style=style,
            confirm=confirm,
            confirm_message=confirm_message,
            preview_before_confirm=preview_before_confirm,
            spinner=spinner,
            spinner_message=spinner_message,
            spinner_type=spinner_type,
            spinner_style=spinner_style,
            spinner_speed=spinner_speed,
            tags=tags if tags else [],
            logging_hooks=logging_hooks,
            hooks=hooks,
            retry=retry,
            retry_all=retry_all,
            retry_policy=retry_policy,
            options_manager=options_manager,
            arg_parser=arg_parser,
            execution_options=parsed_execution_options,
            arguments=arguments or [],
            argument_config=argument_config,
            custom_parser=custom_parser,
            custom_help=custom_help,
            custom_tldr=custom_tldr,
            auto_args=auto_args,
            arg_metadata=arg_metadata or {},
            simple_help_signature=simple_help_signature,
            ignore_in_history=ignore_in_history,
            program=program,
        )

        for hook in before_hooks or []:
            command.hooks.register(HookType.BEFORE, hook)
        for hook in success_hooks or []:
            command.hooks.register(HookType.ON_SUCCESS, hook)
        for hook in error_hooks or []:
            command.hooks.register(HookType.ON_ERROR, hook)
        for hook in after_hooks or []:
            command.hooks.register(HookType.AFTER, hook)
        for hook in teardown_hooks or []:
            command.hooks.register(HookType.ON_TEARDOWN, hook)

        if spinner:
            command.hooks.register(HookType.BEFORE, spinner_before_hook)
            command.hooks.register(HookType.ON_TEARDOWN, spinner_teardown_hook)

        return command
