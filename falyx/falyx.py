# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Core application runtime for the Falyx CLI framework.

This module defines `Falyx`, the top-level orchestration layer used to build,
route, render, and execute Falyx applications. `Falyx` sits above individual
`Command` objects and their local argument parsers.

Core Responsibilities:
- Registration of commands, builtins, and nested namespaces
- Root/session option parsing
- Recursive namespace-aware routing
- Interactive menu prompting and validation
- Routed autocompletion
- Namespace and command help/TLDR rendering
- Execution dispatch through `CommandExecutor`
- Shared option state and execution history

Architecture:
    Falyx is the routing boundary of the framework.

    - `FalyxParser` parses only root-level/session flags and leaves the remaining
      tokens untouched for routing.
    - `Falyx.resolve_route()` walks the invocation path recursively across
      nested `FalyxNamespace` entries until it reaches either a namespace help
      target, a namespace menu target, an unknown entry, or a leaf `Command`.
    - Once a leaf command is found, command-local parsing is delegated to that
      command's `CommandArgumentParser` via `Command.resolve_args()`.
    - Prepared inputs are then executed through `CommandExecutor`, which applies
      shared outer execution behavior consistently across CLI and menu flows.

Execution Model:
    1. Root CLI/session flags are parsed.
    2. The remaining tokens are routed across namespaces and commands.
    3. If a leaf command is reached, its remaining argv is parsed locally.
    4. The resolved route is rendered, previewed, or executed.
    5. Shared hooks, option overrides, and execution tracking are applied.

Interactive Features:
    In menu mode, `Falyx` integrates Rich and Prompt Toolkit to provide a
    structured interactive runtime with:

    - persistent prompt history
    - routed validation
    - namespace-aware autocompletion
    - bottom-bar rendering and key bindings
    - preview flows and contextual help
    - history and built-in utility commands

Design Notes:
    - `Falyx` owns routing; commands own leaf argument parsing; the executor owns
      outer execution behavior.
    - CLI mode and menu mode share the same routed execution semantics.
    - Help, usage, and TLDR rendering are invocation-context aware so nested
      namespaces display correctly scoped command paths.
    - Builtins such as help, preview, version, history, and exit are registered
      as first-class entries within the application runtime.

This module is the primary entrypoint for assembling and running a Falyx
application.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
import sys
from difflib import get_close_matches
from functools import cached_property
from pathlib import Path
from random import choice
from typing import Any, Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.application import get_app
from prompt_toolkit.formatted_text import StyleAndTextTuples
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.validation import ValidationError
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
from rich.style import StyleType
from rich.table import Table
from rich.text import Text

from falyx.action.action import Action
from falyx.action.base_action import BaseAction
from falyx.action.signal_action import SignalAction
from falyx.bottom_bar import BottomBar
from falyx.command import Command
from falyx.command_executor import CommandExecutor
from falyx.completer import FalyxCompleter
from falyx.completer_types import CompletionRoute
from falyx.console import console, error_console, print_error
from falyx.context import InvocationContext
from falyx.debug import log_after, log_before, log_error, log_success
from falyx.exceptions import (
    CommandAlreadyExistsError,
    CommandArgumentError,
    EntryNotFoundError,
    FalyxError,
    InvalidActionError,
    InvalidHookError,
    NotAFalyxError,
    UsageError,
)
from falyx.execution_option import ExecutionOption
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.logger import logger
from falyx.mode import FalyxMode
from falyx.namespace import FalyxNamespace
from falyx.options_manager import OptionsManager
from falyx.parser import CommandArgumentParser, FalyxParser, ParseResult
from falyx.parser.parser_types import FalyxTLDRInput
from falyx.prompt_utils import rich_text_to_prompt_text
from falyx.protocols import ArgParserProtocol
from falyx.retry import RetryPolicy
from falyx.routing import RouteKind, RouteResult
from falyx.signals import BackSignal, CancelSignal, FlowSignal, HelpSignal, QuitSignal
from falyx.themes import OneColors
from falyx.utils import CaseInsensitiveDict, chunks
from falyx.validators import CommandValidator
from falyx.version import __version__


# TODO: better OptionsManager determination (assert same instance across a namespace)
class Falyx:
    """Primary controller for Falyx CLI applications.

    `Falyx` manages the full runtime of a Falyx application, including command
    registration, nested namespace traversal, interactive menu behavior, routed
    help output, and execution dispatch.

    It acts as the central integration point between:
    - Command definitions (`Command`)
    - Nested namespaces (`FalyxNamespace`)
    - Root parser (`FalyxParser`)
    - Leaf argument parsers (`CommandArgumentParser`)
    - Execution dispatch (`CommandExecutor`)
    - Execution units (`Action`, `ChainedAction`, `ActionGroup`)
    - Shared runtime configuration (`OptionsManager`)
    - Lifecycle hooks (`HookManager`)
    - UI layers (Rich + Prompt Toolkit)

    Key Responsibilities:
    - Maintain a registry of commands, aliases, builtins, and namespaces
    - Parse root-level/session flags and delegate the rest to routing
    - Resolve user input to a routed `RouteResult`
    - Provide namespace-aware completion and validation
    - Execute commands with full lifecycle hook support
    - Provide prepared command executions through the shared executor
    - Render help, usage, and TLDR output with invocation context
    - Apply execution-scoped option overrides (e.g. confirm, retries)
    - Manage prompt session state, history, and bottom-bar integration
    - Record and surface execution

    Routing Model:
        `Falyx` performs recursive routing across visible entries in the current
        namespace.

        - If no entry is selected, the route may target the current namespace
          itself.
        - If a help or TLDR flag is encountered before a leaf command, the route
          targets namespace help for the current scope.
        - If a namespace entry is selected, routing continues inside that nested
          `Falyx` instance.
        - If a leaf command is selected, the remaining argv is preserved and
          delegated unchanged to that command's parser.

        This keeps namespace traversal separate from command-local parsing and
        ensures completion, validation, help rendering, and execution all share
        the same routing semantics.

    Execution Semantics:
        `Falyx` does not parse command-local arguments itself once a leaf command
        is resolved. Instead, it prepares the route, delegates leaf parsing to
        the selected command, and forwards the prepared `(args, kwargs,
        execution_args)` to `CommandExecutor`.

        This separation preserves a clean boundary:

        - `Falyx` routes
        - `Command` parses
        - `CommandExecutor` executes

    Interactive Semantics:
        In menu mode, `Falyx` provides a prompt-driven interface with routed
        validation and completion. In CLI mode, it applies the same routing and
        execution pipeline to raw argv-style input. Both modes therefore share
        the same command behavior, help model, and execution lifecycle.

    Design Notes:
    - Commands are first-class and may encapsulate complex workflows
    - Execution options are parsed separately from command arguments
    - All execution passes through a unified hook lifecycle

    Attributes:
        title (str | Markdown): Display title for the interactive menu.
        program (str): Program name used in CLI-facing help and invocation paths.
        commands (dict[str, Command]): Registered user commands.
        builtins (dict[str, Command]): Registered built-in commands such as help,
            preview, and version.
        namespaces (dict[str, FalyxNamespace]): Registered nested namespaces.
        options (OptionsManager): Shared runtime option manager.
        hooks (HookManager): Application-level hook manager.
        console (Console): Rich console used for rendering output.
        key_bindings (KeyBindings): Prompt Toolkit key bindings for menu mode.
        bottom_bar (BottomBar | str | Callable | None): Bottom toolbar renderer.
        history (FileHistory | None): Optional persistent prompt history backend.

    Raises:
        FalyxError: If invalid configuration or command registration occurs.
        CommandAlreadyExistsError: If a command, alias, or namespace identifier
            collides with an existing entry.

    Notes:
        - Entry names are resolved case-insensitively.
        - Builtins and namespaces participate in the same routing surface as
          normal commands.
        - Help, TLDR, and usage rendering are scoped by `InvocationContext`,
          which allows nested namespaces to render accurate command paths.
    """

    def __init__(
        self,
        title: str = "Menu",
        *,
        program: str | None = "falyx",
        usage: str | None = None,
        description: str | None = "Falyx CLI - Run structured async command workflows.",
        epilog: str | None = None,
        caption: str | None = None,
        version: str = __version__,
        title_style: StyleType = "white bold",
        program_style: StyleType = OneColors.BLUE_b,
        usage_style: StyleType = "white",
        description_style: StyleType = OneColors.BLUE,
        epilog_style: StyleType = "white",
        caption_style: StyleType = "white",
        version_style: StyleType = OneColors.BLUE_b,
        prompt: str | StyleAndTextTuples = "> ",
        columns: int = 3,
        bottom_bar: BottomBar | str | Callable[[], Any] | None = None,
        welcome_message: str = "",
        exit_message: str = "",
        key_bindings: KeyBindings | None = None,
        include_history_command: bool = True,
        never_prompt: bool = False,
        force_confirm: bool = False,
        verbose: bool = False,
        debug_hooks: bool = False,
        options: OptionsManager | None = None,
        render_menu: Callable[[Falyx], None] | None = None,
        custom_table: Callable[[Falyx], Table] | Table | None = None,
        hide_menu_table: bool = False,
        show_placeholder_menu: bool = False,
        prompt_history_base_dir: Path = Path.home(),
        enable_prompt_history: bool = False,
        enable_help_tips: bool = True,
        default_to_menu: bool = True,
        simple_usage: bool = False,
        disable_verbose_option: bool = False,
        disable_debug_hooks_option: bool = False,
        disable_never_prompt_option: bool = False,
    ) -> None:
        """Initialize a Falyx application runtime.

        This constructor configures the top-level application object used to run a
        Falyx CLI or interactive menu. It establishes the shared runtime state for
        command registration, namespace routing, menu rendering, prompt behavior,
        built-in command availability, and executor-backed dispatch.

        During initialization, `Falyx`:

        - stores application display metadata such as title, description, and version
        - creates or validates the shared `OptionsManager`
        - prepares key bindings, prompt rendering, and optional bottom-bar behavior
        - initializes registries for commands, builtins, and namespaces
        - registers default built-in commands such as help, preview, and version
        - optionally enables persistent prompt history
        - creates the shared `CommandExecutor` used for command dispatch

        The resulting instance is ready to have commands and namespaces added before
        being executed in CLI or menu mode.

        Args:
            title (str): Title displayed for the interactive menu or top-level
                application view.
            program (str | None): Program name used in CLI usage text, invocation-path
                rendering, and built-in help output. If `None`, an empty program name is
                used.
            usage (str | None): Optional usage override for namespace-level CLI help. When
                omitted, usage text is derived from the current invocation context.
            description (str | None): Short program description shown in top-level help
                output.
            epilog (str | None): Optional trailing help text rendered after the main help
                sections.
            version (str): Application version string used by the built-in version command.
            program_style (StyleType): Rich style used when rendering the program name.
            usage_style (StyleType): Rich style used for rendered usage text.
            description_style (StyleType): Rich style used for the program description.
            epilog_style (StyleType): Rich style used for the help epilog.
            version_style (StyleType): Rich style used for version output and version-related
                rendering.
            prompt (str | StyleAndTextTuples): Prompt text or Prompt Toolkit formatted text
                shown in menu mode.
            columns (int): Default column count used by menu-oriented UI components such as
                the bottom bar.
            bottom_bar (BottomBar | str | Callable[[], Any] | None): Bottom toolbar
                configuration for menu mode. May be a `BottomBar` instance, a static
                string, a callable renderer, or `None` to use the default bottom bar.
            welcome_message (str): Optional welcome content
                rendered when entering the interactive menu.
            exit_message (str): Optional exit content rendered
                when leaving the interactive menu.
            key_bindings (KeyBindings | None): Optional Prompt Toolkit key bindings for
                menu interaction. If omitted, a default `KeyBindings` object is created.
            include_history_command (bool): Whether to register the built-in history
                command.
            never_prompt (bool): Default session-level value for the `never_prompt`
                runtime option.
            force_confirm (bool): Default session-level value for the `force_confirm`
                runtime option.
            verbose (bool): Default session-level value for the `verbose` runtime option.
            debug_hooks (bool): Default session-level value for the `debug_hooks` runtime option.
            options (OptionsManager | None): Shared options manager for the application.
                If omitted, a new `OptionsManager` instance is created.
            render_menu (Callable[[Falyx], None] | None): Optional custom menu renderer
                used instead of the default table-based menu output.
            custom_table (Callable[[Falyx], Table] | Table | None): Optional custom Rich
                table or table factory used when rendering the default menu view.
            hide_menu_table (bool): Whether the default menu table should be hidden.
            show_placeholder_menu (bool): Whether prompt placeholder content should be
                shown in the interactive prompt.
            prompt_history_base_dir (Path): Base directory used to store persistent prompt
                history files when history is enabled.
            enable_prompt_history (bool): Whether to persist Prompt Toolkit input history
                to disk.
            enable_help_tips (bool): Whether to show contextual usage tips in rendered
                help output.
            default_to_menu (bool): Whether to enter menu mode if no CLI arguments are
                provided on startup. If `False`, the application will print help and
                exit when no arguments are provided.
            simple_usage (bool): Whether to use a simplified usage format in help output.
            disable_verbose_option (bool): Whether to omit the built-in `--verbose` option
                from the root parser.
            disable_debug_hooks_option (bool): Whether to omit the built-in `--debug-hooks`
                option from the root parser.
            disable_never_prompt_option (bool): Whether to omit the built-in `--never-prompt`
                option from the root parser.

        Raises:
            FalyxError: If the provided options object is invalid or other core runtime
                configuration is inconsistent.

        Notes:
            - Initialization does not execute commands or parse user input.
            - Default built-ins are registered immediately so they participate in routing,
            completion, and help rendering from the start.
            - The prompt session itself is created lazily, allowing UI-related state such
            as bottom bars and key bindings to be finalized before first use.
        """
        self.title: str = title
        self.program: str = program or ""
        self.usage: str | None = usage
        self.description: str | None = description
        self.epilog: str | None = epilog
        self.caption: str | None = caption
        self.version: str = version
        self.title_style: StyleType = title_style
        self.program_style: StyleType = program_style
        self.usage_style: StyleType = usage_style
        self.description_style: StyleType = description_style
        self.epilog_style: StyleType = epilog_style
        self.caption_style: StyleType = caption_style
        self.version_style: StyleType = version_style
        self.prompt: str | StyleAndTextTuples = rich_text_to_prompt_text(prompt)
        self.columns: int = columns
        self.commands: dict[str, Command] = CaseInsensitiveDict()
        self.builtins: dict[str, Command] = CaseInsensitiveDict()
        self.namespaces: dict[str, FalyxNamespace] = CaseInsensitiveDict()
        self.console: Console = console
        self.error_console: Console = error_console
        self.welcome_message: str = welcome_message
        self.exit_message: str = exit_message
        self.hooks: HookManager = HookManager()
        self.key_bindings: KeyBindings = key_bindings or KeyBindings()
        self.bottom_bar: BottomBar | str | Callable[[], None] | None = bottom_bar
        self._never_prompt: bool = never_prompt
        self._force_confirm: bool = force_confirm
        self._verbose: bool = verbose
        self._debug_hooks: bool = debug_hooks
        self.render_menu: Callable[[Falyx], None] | None = render_menu
        self.custom_table: Callable[[Falyx], Table] | Table | None = custom_table
        self._hide_menu_table: bool = hide_menu_table
        self.show_placeholder_menu: bool = show_placeholder_menu
        self._validate_options(options)
        self._prompt_session: PromptSession | None = None
        self.options.set("mode", FalyxMode.COMMAND)
        self.exit_command: Command = self._get_exit_command()
        self.history_command: Command | None = (
            self._get_history_command() if include_history_command else None
        )
        self.help_command: Command = self._get_help_command()
        if enable_prompt_history:
            program = (program or "falyx").split(".")[0].replace(" ", "_")
            self.history_path: Path = (
                Path(prompt_history_base_dir) / f".{program}_history"
            )
            self.history: FileHistory | None = FileHistory(self.history_path)
        else:
            self.history = None
        self.enable_help_tips: bool = enable_help_tips
        self.default_to_menu: bool = default_to_menu
        self.simple_usage: bool = simple_usage
        self._register_default_builtins()
        self._register_options()
        self._executor = CommandExecutor(
            options=self.options,
            hooks=self.hooks,
        )
        self.disable_verbose_option: bool = disable_verbose_option
        self.disable_debug_hooks_option: bool = disable_debug_hooks_option
        self.disable_never_prompt_option: bool = disable_never_prompt_option
        self.parser: FalyxParser = FalyxParser(self)

    def add_tldr_example(
        self,
        *,
        entry_key: str,
        usage: str,
        description: str,
    ) -> None:
        """Register a single namespace-level TLDR example.

        The referenced entry must resolve to a known command or namespace in the
        current `Falyx` instance. Unknown entries are reported to the console and
        are not added.

        Args:
            entry_key (str): Command or namespace key the example is associated with.
            usage (str): Example usage fragment shown after the resolved invocation path.
            description (str): Short explanation displayed alongside the example.

        Raises:
            EntryNotFoundError: If `entry_key` cannot be resolved to a known command or
                namespace in this `Falyx` instance.
        """
        self.parser.add_tldr_example(
            entry_key=entry_key,
            usage=usage,
            description=description,
        )

    def add_tldr_examples(self, examples: list[FalyxTLDRInput]) -> None:
        """Register multiple namespace-level TLDR examples.

        Supports either `FalyxTLDRExample` objects or shorthand tuples of
        `(entry_key, usage, description)`.

        Args:
            examples (list[FalyxTLDRInput]): Example definitions to validate and append.

        Raises:
            FalyxError: If an example has an unsupported shape.
            EntryNotFoundError: If `entry_key` cannot be resolved to a known command or
                namespace in this `Falyx` instance.
        """
        self.parser.add_tldr_examples(examples)

    def get_current_invocation_context(self) -> InvocationContext:
        """Build the default invocation context for this namespace.

        The returned context starts at the current namespace root and reflects the
        runtime mode stored in the shared options manager.

        Returns:
            InvocationContext: Fresh invocation context for help, routing, or
            completion.
        """
        return InvocationContext(
            program=self.program,
            program_style=self.program_style,
            typed_path=[],
            mode=self.options.get("mode"),
        )

    @property
    def _is_cli_mode(self) -> bool:
        """Return whether the application is currently running outside menu mode.

        Returns:
            bool: `True` when the active mode is not `FalyxMode.MENU`.
        """
        return self.options.get("mode") != FalyxMode.MENU

    def _validate_options(
        self,
        options: OptionsManager | None = None,
    ) -> None:
        """Validate and install the shared options manager.

        If no options manager is provided, a new `OptionsManager` is created and
        stored on the instance.

        Args:
            options (OptionsManager | None): Optional options manager to reuse.

        Raises:
            NotAFalyxError: If `options` is provided but is not an `OptionsManager`.
        """
        self.options: OptionsManager = options or OptionsManager()
        if not isinstance(self.options, OptionsManager):
            raise NotAFalyxError("options must be an instance of OptionsManager.")

    def _register_options(self) -> None:
        """Seed default application options and execution namespace values.

        This method ensures that core runtime flags such as mode, prompt behavior,
        menu visibility, and program display metadata exist in the shared options
        manager.
        """
        self.options.from_mapping(values={}, namespace_name="execution")

        if not self.options.get("never_prompt"):
            self.options.set("never_prompt", self._never_prompt)

        if not self.options.get("force_confirm"):
            self.options.set("force_confirm", self._force_confirm)

        if not self.options.get("verbose"):
            self.options.set("verbose", self._verbose)

        if not self.options.get("debug_hooks"):
            self.options.set("debug_hooks", self._debug_hooks)

        if not self.options.get("hide_menu_table"):
            self.options.set("hide_menu_table", self._hide_menu_table)

        if not self.options.get("program"):
            self.options.set("program", self.program)

        if not self.options.get("program_style"):
            self.options.set("program_style", self.program_style)

    @property
    def completion_names(self) -> list[str]:
        """Return the visible names exposed for namespace completion.

        The result includes command keys, command aliases, namespace keys,
        namespace aliases, builtins, and special entries such as history and exit,
        while deduplicating names case-insensitively.

        Returns:
            list[str]: Visible completion candidates for this namespace.
        """
        names: list[str] = []
        seen: set[str] = set()

        def add(name: str) -> None:
            normalized = name.upper().strip()
            if normalized not in seen:
                seen.add(normalized)
                names.append(name)

        for command in self.commands.values():
            if not command.hidden:
                add(command.key)
                for alias in command.aliases:
                    add(alias)

        for namespace in self.namespaces.values():
            if not namespace.hidden:
                add(namespace.key)
                for alias in namespace.aliases:
                    add(alias)

        for command in self.builtins.values():
            if not command.hidden:
                add(command.key)
                for alias in command.aliases:
                    add(alias)

        if self.history_command and not self.history_command.hidden:
            add(self.history_command.key)
            for alias in self.history_command.aliases:
                add(alias)

        add(self.exit_command.key)
        for alias in self.exit_command.aliases:
            add(alias)

        return names

    @property
    def _entry_map(self) -> dict[str, Command | FalyxNamespace]:
        """Build a case-insensitive lookup map for all resolvable entries.

        The map includes commands, namespaces, builtins, history, and exit
        entries. Descriptions are also registered for commands and builtins to
        support friendly lookup behavior.

        Returns:
            dict[str, Command | FalyxNamespace]: Normalized identifier-to-entry map.

        Raises:
            CommandAlreadyExistsError: If two distinct entries claim the same
                normalized identifier.
        """
        mapping: dict[str, Command | FalyxNamespace] = {}

        def register(name: str, entry: Command | FalyxNamespace):
            norm = name.upper().strip()
            if norm in mapping:
                existing = mapping[norm]
                if existing is not entry:
                    raise CommandAlreadyExistsError(
                        f"identifier '{norm}' is already registered.\n"
                        f"existing entry: {mapping[norm].key}\n"
                        f"new entry: {entry.key}"
                    )
            else:
                mapping[norm] = entry

        for command in self.commands.values():
            register(command.key, command)
            for alias in command.aliases:
                register(alias, command)
            register(command.description, command)

        for namespace in self.namespaces.values():
            register(namespace.key, namespace)
            for alias in namespace.aliases:
                register(alias, namespace)

        for command in self.builtins.values():
            register(command.key, command)
            for alias in command.aliases:
                register(alias, command)
            register(command.description, command)

        for special in [self.history_command, self.exit_command]:
            if special:
                register(special.key, special)
                for alias in special.aliases:
                    register(alias, special)
                register(special.description, special)

        return mapping

    def _get_exit_command(self) -> Command:
        """Create the default exit command for this namespace.

        The default entry emits a `QuitSignal`, is excluded from history-sensitive
        behavior, and is rendered with the namespace's shared options manager.

        Returns:
            Command: Configured exit command instance.
        """
        exit_command = Command(
            key="X",
            description="Exit",
            action=SignalAction("Exit", QuitSignal()),
            aliases=["EXIT", "QUIT"],
            style=OneColors.DARK_RED,
            simple_help_signature=True,
            ignore_in_history=True,
            options_manager=self.options,
            program=self.program,
            help_text="Exit the program.",
        )
        if exit_command.arg_parser:
            exit_command.arg_parser.add_tldr_examples([("", "Exit the program.")])
        return exit_command

    def _get_history_command(self) -> Command:
        """Create the built-in execution-history command.

        The returned command wraps `ExecutionRegistry.summary` and includes a
        purpose-built parser for history filtering, clearing, and result lookup.

        Returns:
            Command: Configured history command instance.
        """

        def add_history_arguments(parser: CommandArgumentParser) -> None:
            parser.add_argument(
                "-n",
                "--name",
                help="Filter by execution name.",
            )
            parser.add_argument(
                "-i",
                "--index",
                type=int,
                help="Filter by execution index (0-based).",
            )
            parser.add_argument(
                "-s",
                "--status",
                choices=["all", "success", "error"],
                default="all",
                help="Filter by execution status (default: all).",
            )
            parser.add_argument(
                "-c",
                "--clear",
                action="store_true",
                help="Clear the Execution History.",
            )
            parser.add_argument(
                "-r",
                "--result-index",
                type=int,
                help="Get the result by index",
            )
            parser.add_argument(
                "-l", "--last-result", action="store_true", help="Get the last result"
            )
            parser.add_tldr_examples(
                [
                    ("", "Show the full execution history."),
                    ("-n build", "Show history entries for the 'build' command."),
                    ("-s success", "Show only successful executions."),
                    ("-s error", "Show only failed executions."),
                    ("-i 3", "Show the history entry at index 3."),
                    ("-r 0", "Show the result or traceback for entry index 0."),
                    ("-l", "Show the last execution result."),
                    ("-c", "Clear the execution history."),
                ]
            )

        return Command(
            key="Y",
            description="History",
            aliases=["HISTORY"],
            action=Action(name="View Execution History", action=er.summary),
            style=OneColors.DARK_YELLOW,
            argument_config=add_history_arguments,
            help_text="View the execution history of commands.",
            ignore_in_history=True,
            options_manager=self.options,
            program=self.program,
        )

    def get_tip(self) -> str:
        """Return a random usage tip appropriate for the current runtime mode.

        Tips differ slightly between CLI and menu mode so the user sees examples
        that match the active interface.

        Returns:
            str: One formatted help tip.
        """
        program = f"{self.program} " if self._is_cli_mode else ""
        tips = [
            f"Use '{program}?[COMMAND]' to preview a command.",
            "Every command supports aliases—try abbreviating the name!",
            f"Use '{program}H' to reopen this help menu anytime.",
            f"'{program}[COMMAND] --help' prints a detailed help message.",
            "[bold]CLI[/] and [bold]Menu[/] mode—commands run the same way in both.",
            f"'{self.program} --never-prompt' to disable all prompts for the [bold italic]entire menu session[/].",
            f"Use '{self.program} --verbose' to enable debug logging for a menu session.",
            f"'{self.program} --debug-hooks' will trace every before/after hook in action.",
            f"Run commands directly from the CLI: '{self.program} [COMMAND] [OPTIONS]'.",
            "All [COMMAND] keys and aliases are case-insensitive.",
        ]
        if self._is_cli_mode:
            tips.extend(
                [
                    f"Use '{self.program} help' to list all commands at any time.",
                    f"Use '{self.program} --never-prompt [COMMAND] [OPTIONS]' to disable all prompts for [bold italic]just this command[/].",
                    f"Use '{self.program} --skip-confirm [COMMAND] [OPTIONS]' to skip confirmations.",
                    f"Use '{self.program} --summary [COMMAND] [OPTIONS]' to print a post-run summary.",
                    f"Use '{self.program} --verbose [COMMAND] [OPTIONS]' to enable debug logging for any run.",
                    "Use '--skip-confirm' for automation scripts where no prompts are wanted.",
                ]
            )
        else:
            tips.extend(
                [
                    "Use '[?]' alone to list all commands at any time.",
                    "'[CTRL+KEY]' toggles are available in menu mode for quick switches.",
                    "'[Y]' opens the command history viewer.",
                    "Use '[X]' in menu mode to exit.",
                ]
            )
        return choice(tips)

    def _get_command_keys_usage_string(self) -> str:
        """Build a usage string fragment representing the available command keys.

        This method gathers all visible command and builtin keys, and formats them in a
        '|' separated string suitable for inclusion in usage text.

        Returns:
            str: Formatted usage fragment containing available command keys.
        """
        keys = [
            f"[{command.style}]{command.key}[/{command.style}]"
            for command in self.commands.values()
            if not command.hidden
        ]
        keys.extend(
            [
                f"[{namespace.style}]{namespace.key}[/{namespace.style}]"
                for namespace in self.namespaces.values()
                if not namespace.hidden
            ]
        )
        keys.extend(
            [
                f"[{command.style}]{command.key}[/{command.style}]"
                for command in self.builtins.values()
                if not command.hidden
            ]
        )
        if not self._is_cli_mode:
            if self.history_command and not self.history_command.hidden:
                keys.append(
                    f"[{self.history_command.style}]{self.history_command.key}[/{self.history_command.style}]"
                )
            keys.append(
                f"[{self.exit_command.style}]{self.exit_command.key}[/{self.exit_command.style}]"
            )
        return "|".join(keys)

    def _get_usage_fragment(self, invocation_context: InvocationContext) -> str:
        """Build the default namespace usage fragment for the given context.

        Usage text will contain all commands and namespaces if `simple_usage` is
        disabled, or a generic placeholder if `simple_usage` is enabled.
        If `simple_usage` is enabled, the usage fragment is simplified to a generic
        placeholder format.

        Args:
            invocation_context (InvocationContext): Routed invocation context for
                the current help target.

        Returns:
            str: Escaped usage fragment suitable for Rich output.
        """
        has_namespaces = any(not ns.hidden for ns in self.namespaces.values())

        root_flags = " ".join(
            f"{escape(f"[{flag}]")}" for flag in self.parser.get_flags()
        )

        if self.simple_usage:
            target = "command or namespace" if has_namespaces else "command"
        else:
            target = self._get_command_keys_usage_string()
        return f"{root_flags} <{target}> {escape('[args...]')}"

    def _get_usage(
        self,
        invocation_context: InvocationContext | None = None,
    ) -> str:
        """Build usage information for the current namespace.

        This method builds a usage string based on the current invocation context
        and renders it to the console with appropriate styling.

        Args:
            invocation_context (InvocationContext | None): Routed invocation context for
                the current help target.
        """
        invocation_context = invocation_context or self.get_current_invocation_context()
        usage = self.usage or self._get_usage_fragment(invocation_context)
        if self._is_cli_mode:
            return f"[bold]usage:[/bold] {invocation_context.markup_path} [{self.usage_style}]{usage}[/{self.usage_style}]"
        return f"[bold]usage:[/bold] [{self.usage_style}]{usage}[/{self.usage_style}]"

    def render_usage(
        self,
        invocation_context: InvocationContext | None = None,
    ) -> None:
        """Public method to render usage information for the current namespace.

        This method is a public wrapper around `_get_usage` that can be called
        from commands or hooks to display usage information in the current context.

        Args:
            invocation_context (InvocationContext | None): Routed invocation context for
                the current help target.
        """
        usage = self._get_usage(invocation_context)
        console.print(usage)

    async def _render_command_tldr(
        self,
        command: Command,
        invocation_context: InvocationContext | None = None,
    ) -> None:
        """Render TLDR examples for a resolved command.

        This helper validates that the supplied entry is a command, delegates TLDR
        rendering to that command, and optionally appends a random usage tip.

        Args:
            command (Command): Command whose TLDR output should be shown.
            invocation_context (InvocationContext | None): Optional routed invocation
                context used to scope the rendered usage path.
        """
        if command.render_tldr(invocation_context):
            if self.enable_help_tips:
                self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")
        else:
            print_error(f"No TLDR examples available for '{command.description}'.")

    async def _render_command_help(
        self,
        command: Command,
        tldr: bool = False,
        invocation_context: InvocationContext | None = None,
    ) -> None:
        """Render detailed help or TLDR output for a resolved command.

        Args:
            command (Command): Target command to render.
            tldr (bool): When `True`, render TLDR output instead of full help.
            invocation_context (InvocationContext | None): Optional routed invocation
                context used to scope the rendered usage path.
        """
        if tldr:
            await self._render_command_tldr(command, invocation_context)
        elif command.render_help(invocation_context):
            if self.enable_help_tips:
                self.console.print(f"\n[bold]tip:[/bold] {self.get_tip()}")
        else:
            print_error(f"No detailed help available for '{command.description}'.")

    async def _render_tag_help(self, tag: str) -> None:
        """Render all visible commands associated with a tag.

        Matching is case-insensitive and only searches user-registered commands,
        not namespaces or builtins.

        Args:
            tag (str): Tag name to filter by.
        """
        tag_lower = tag.lower()
        self.console.print(f"[bold]{tag_lower}:[/bold]")
        commands = [
            command
            for command in self.commands.values()
            if any(tag_lower == tag.lower() for tag in command.tags)
        ]
        if not commands:
            self.console.print(f"'{tag}'... Nothing to show here")
            return None
        for command in commands:
            usage, description, _ = command.help_signature
            self.console.print(
                Padding(
                    Panel(usage, expand=False, title=description, title_align="left"),
                    (0, 2),
                )
            )
        if self.enable_help_tips:
            self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")

    async def _render_menu_help(self, invocation_context: InvocationContext) -> None:
        """Render the interactive menu-style help view for this namespace.

        The menu help view displays user commands plus the special help, history,
        and exit entries using panel-based Rich rendering.
        """
        self.render_usage(invocation_context)
        if self.description:
            self.console.print(
                f"\n[{self.description_style}]{self.description}[/{self.description_style}]"
            )

        # TODO: implement self.parser.render_options_help() and include it here if options are registered at the namespace level
        self.console.print("\n[bold]global options:[/bold]")
        for option in self.parser.get_options():
            self.console.print(f"  {option.format_for_help():<22}{option.help}")

        self.console.print("\n[bold]builtin commands:[/bold]")
        for command in self.builtins.values():
            usage, description, _ = command.help_signature
            self.console.print(
                Padding(
                    Panel(usage, expand=False, title=description, title_align="left"),
                    (0, 2),
                )
            )
        if self.history_command:
            usage, description, _ = self.history_command.help_signature
            self.console.print(
                Padding(
                    Panel(usage, expand=False, title=description, title_align="left"),
                    (0, 2),
                )
            )
        usage, description, _ = self.exit_command.help_signature
        self.console.print(
            Padding(
                Panel(usage, expand=False, title=description, title_align="left"),
                (0, 2),
            )
        )
        if self.namespaces:
            self.console.print("\n[bold]namespaces:[/bold]")
            for namespace in self.namespaces.values():
                usage, description, _ = namespace.get_help_signature(invocation_context)
                self.console.print(
                    Padding(
                        Panel(usage, expand=False, title=description, title_align="left"),
                        (0, 2),
                    )
                )

        if self.commands:
            self.console.print("\n[bold]commands:[/bold]")
            for command in self.commands.values():
                usage, description, tag = command.help_signature
                self.console.print(
                    Padding(
                        Panel(
                            usage,
                            expand=False,
                            title=description,
                            title_align="left",
                            subtitle=tag,
                        ),
                        (0, 2),
                    )
                )

        if self.epilog:
            self.console.print(f"\n{self.epilog}", style=self.epilog_style)
        if self.enable_help_tips:
            self.console.print(f"\n[bold]tip:[/bold] {self.get_tip()}")

    async def _render_namespace_tldr_help(
        self, invocation_context: InvocationContext
    ) -> None:
        """Render namespace-level TLDR examples for the current scope.

        This prints usage, optional namespace description, and all registered TLDR
        examples using the routed invocation path supplied by the context.

        Args:
            invocation_context (InvocationContext): Routed invocation context for the
                namespace being rendered.
        """
        if not self.parser.tldr_option:
            self.console.print(
                f"[bold]No TLDR examples available for '{self.title}'.[/bold]"
            )
            return None
        self.render_usage(invocation_context)
        prefix = invocation_context.markup_path
        if self.description:
            self.console.print(
                f"\n[{self.description_style}]{self.description}[/{self.description_style}]"
            )
        self.console.print("\n[bold]examples:[/bold]")
        for example in self.parser._tldr_examples:
            entry, suggestions = self.resolve_entry(example.entry_key)
            if not entry:
                raise EntryNotFoundError(
                    unknown_name=example.entry_key,
                    suggestions=suggestions,
                    message_context="TLDR example",
                )
            command = f"[{entry.style}]{example.entry_key}[/{entry.style}]"
            usage = f"{prefix} {command} {example.usage.strip()}"
            description = example.description.strip()
            block = f"[bold]{usage}[/bold]"
            self.console.print(
                Padding(
                    Panel(block, expand=False, title=description, title_align="left"),
                    (0, 2),
                )
            )

    async def render_namespace_help(
        self,
        invocation_context: InvocationContext | None = None,
        tldr: bool = False,
    ) -> None:
        """Render help for the current namespace.

        Depending on the active mode and flags, this dispatches to namespace TLDR,
        menu-style help, or CLI-style help rendering.

        Args:
            invocation_context (InvocationContext | None): Optional routed invocation
                context. When omitted, a fresh root context is created.
            tldr (bool): Whether to render namespace TLDR output instead of standard help.
        """
        invocation_context = invocation_context or self.get_current_invocation_context()
        if tldr:
            await self._render_namespace_tldr_help(invocation_context)
        elif invocation_context.mode is FalyxMode.MENU:
            await self._render_menu_help(invocation_context)
        else:
            await self._render_cli_help(invocation_context)

    async def _render_cli_help(self, invocation_context: InvocationContext) -> None:
        """Render the CLI-style help view for this namespace.

        The output includes usage, description, global options, builtin commands,
        user commands, and optional epilog content.

        Args:
            invocation_context (InvocationContext): Routed invocation context used to
                render the current invocation path.
        """
        self.render_usage(invocation_context)
        if self.description:
            self.console.print(
                f"\n[{self.description_style}]{self.description}[/{self.description_style}]"
            )
        # TODO: implement self.parser.render_options_help() and include it here if options are registered at the namespace level
        self.console.print("\n[bold]global options:[/bold]")
        for option in self.parser.get_options():
            self.console.print(f"  {option.format_for_help():<22}{option.help}")

        self.console.print("\n[bold]builtin commands:[/bold]")
        for command in self.builtins.values():
            builtin_alias = Text(command.primary_alias, style=command.style)

            line = Text("  ")
            line.append(builtin_alias)
            line.pad_right(24 - len(line.plain))
            line.append(command.help_text)

            self.console.print(line)
        if self.namespaces:
            self.console.print("\n[bold]namespaces:[/bold]")
            for namespace in self.namespaces.values():
                line = Text("  ")
                line.append(namespace.key, style=namespace.style)
                for alias in namespace.aliases:
                    line.append(" | ", style="dim")
                    line.append(alias, style=namespace.style)
                line.pad_right(24 - len(line.plain))
                line.append(namespace.description or "")
                self.console.print(line)
        if self.commands:
            self.console.print("\n[bold]commands:[/bold]")
            for command in self.commands.values():
                line = Text("  ")
                line.append(command.key, style=command.style)
                for alias in command.aliases:
                    line.append(" | ", style="dim")
                    line.append(alias, style=command.style)
                line.pad_right(24 - len(line.plain))
                line.append(command.help_text or command.description)
                self.console.print(line)
        if self.epilog:
            self.console.print(f"\n{self.epilog}", style=self.epilog_style)
        if self.enable_help_tips:
            self.console.print(f"\n[bold]tip:[/bold] {self.get_tip()}")

    def _help_target_base_context(
        self, invocation_context: InvocationContext
    ) -> InvocationContext:
        """Normalize help context before rendering a nested target.

        This strips the trailing help-command segment from the routed path when the
        help command itself is the active entry, preventing duplicated invocation
        paths in nested help output.

        Args:
            invocation_context (InvocationContext): Routed help context to normalize.

        Returns:
            InvocationContext: Adjusted context for downstream help rendering.
        """
        if not invocation_context.typed_path:
            return invocation_context

        last_token = invocation_context.typed_path[-1]
        entry, _ = self.resolve_entry(last_token)

        if entry is self.help_command:
            return invocation_context.without_last_path_segment()

        return invocation_context

    async def render_help(
        self,
        tag: str = "",
        key: str | None = None,
        tldr: bool = False,
        namespace_tldr: bool = False,
        invocation_context: InvocationContext | None = None,
    ) -> None:
        """Render help for a namespace, tag, or specific entry.

        This is the main help dispatcher for `Falyx`. It can render:

        - namespace help for the current scope
        - namespace TLDR output
        - tag-filtered command help
        - command help for a specific key
        - namespace help for a specific nested namespace

        Args:
            tag (str): Optional tag filter for command help.
            key (str | None): Optional command or namespace identifier to render directly.
            tldr (bool): Whether targeted command help should use TLDR output.
            namespace_tldr (bool): Whether top-level namespace help should use TLDR output.
            invocation_context (InvocationContext | None): Optional routed invocation context.

        Raises:
            EntryNotFoundError: If `key` is provided but cannot be resolved to a known command
                or namespace in this scope.
        """
        context = invocation_context or self.get_current_invocation_context()
        if key:
            base_context = self._help_target_base_context(context)

            entry, suggestions = self.resolve_entry(key)
            if isinstance(entry, Command):
                await self._render_command_help(
                    command=entry,
                    tldr=tldr,
                    invocation_context=base_context.with_path_segment(
                        key, style=entry.style
                    ),
                )
            elif isinstance(entry, FalyxNamespace):
                await entry.namespace.render_namespace_help(
                    invocation_context=base_context.with_path_segment(
                        key, style=entry.style
                    ),
                    tldr=tldr,
                )
            else:
                await self.render_namespace_help(base_context)
                raise EntryNotFoundError(
                    unknown_name=key,
                    suggestions=suggestions,
                )
            return None
        elif tldr:
            await self._render_command_help(
                self.help_command,
                tldr,
                invocation_context=context,
            )
        elif tag:
            await self._render_tag_help(tag)
        else:
            await self.render_namespace_help(context, namespace_tldr)

    def _get_help_command(self) -> Command:
        """Create the built-in help command for this namespace.

        The returned command wraps `render_help()` and installs a dedicated parser
        that supports tag filtering, targeted key help, and TLDR behavior.

        Returns:
            Command: Configured help command instance.
        """

        def add_help_arguments(parser: CommandArgumentParser):
            parser.mark_as_help_command()
            parser.add_argument(
                "--namespace-tldr",
                "-N",
                action="store_true",
                help="Show TLDR examples for the namespace instead of full help.",
            )
            parser.add_argument(
                "-t",
                "--tag",
                nargs="?",
                default="",
                help="Optional tag to filter commands by.",
            )
            parser.add_argument(
                "-k",
                "--key",
                nargs="?",
                default=None,
                help="Optional command key or alias to get detailed help for.",
            )
            parser.add_tldr_examples(
                [
                    ("", "Show all commands."),
                    ("-k [COMMAND]", "Show detailed help for a specific command."),
                    (
                        "-Tk [COMMAND]",
                        "Show quick usage examples for a specific command.",
                    ),
                    ("-T", "Show these quick usage examples."),
                    ("-t [TAG]", "Show commands with the specified tag."),
                    ("-N", "Show TLDR examples for the current namespace."),
                ]
            )
            tldr_argument = parser.get_argument("tldr")
            if tldr_argument:
                tldr_argument.help = "Show TLDR examples instead of full help."

        return Command(
            key="H",
            aliases=["HELP", "?"],
            description="Help",
            help_text="Show this help menu.",
            action=Action("Help", self.render_help),
            style=OneColors.LIGHT_YELLOW,
            argument_config=add_help_arguments,
            ignore_in_history=True,
            options_manager=self.options,
            program=self.program,
        )

    async def _preview(self, key: str) -> None:
        """Render a preview for a specific command key.

        Namespaces are rejected because preview is only meaningful at the leaf
        command boundary.

        Args:
            key (str): Command key or alias to preview.
        """
        entry, suggestions = self.resolve_entry(key)
        if isinstance(entry, FalyxNamespace):
            raise FalyxError("preview mode is only supported for commands.")
        elif isinstance(entry, Command):
            await entry.preview()
        else:
            raise EntryNotFoundError(
                unknown_name=key,
                suggestions=suggestions,
            )

    def _get_preview_command(self) -> Command:
        """Create the built-in preview command.

        The preview command accepts a command key or alias and delegates to
        `_preview()`.

        Returns:
            Command: Configured preview command instance.
        """

        def add_preview_argument(parser: CommandArgumentParser):
            parser.add_argument(
                "key",
                help="The key or alias of the command to preview.",
            )
            parser.add_tldr_examples(
                [
                    ("<COMMAND>", "Preview the execution of a specific command."),
                ]
            )

        preview_command = Command(
            key="PVW",
            description="Preview",
            aliases=["PREVIEW"],
            action=Action("Preview", self._preview),
            style=OneColors.GREEN,
            options_manager=self.options,
            program=self.program,
            help_text="Preview the execution of a command without running it.",
            argument_config=add_preview_argument,
        )
        return preview_command

    async def _render_version(self) -> None:
        """Render the program version string for this namespace."""
        self.console.print(f"[{self.version_style}]{self.program} v{self.version}[/]")

    def _get_version_command(self) -> Command:
        """Create the built-in version command.

        Returns:
            Command: Configured version command instance.
        """
        version_command = Command(
            key="VER",
            description="Version",
            aliases=["VERSION"],
            action=Action("Version", self._render_version),
            style=self.version_style,
            ignore_in_history=True,
            options_manager=self.options,
            program=self.program,
            help_text=f"Show the {self.program} version.",
        )
        if version_command.arg_parser:
            version_command.arg_parser.add_tldr_examples(
                [("", f"Show the {self.program} version.")]
            )
        return version_command

    def _add_builtin(self, command: Command) -> None:
        """Register a builtin command in the current namespace.

        Args:
            command (Command): Builtin command to register.

        Raises:
            CommandAlreadyExistsError: If the builtin key or aliases collide with an
                existing identifier.
        """
        self._validate_command_aliases(command.key, command.aliases)
        self.builtins[command.key.upper()] = command
        _ = self._entry_map

    def _register_default_builtins(self) -> None:
        """Register the default help, preview, and version builtins."""
        self._add_builtin(self.help_command)
        self._add_builtin(self._get_preview_command())
        self._add_builtin(self._get_version_command())

    def _get_completer(self) -> FalyxCompleter:
        """Create the Prompt Toolkit completer for this namespace.

        Returns:
            FalyxCompleter: Routing-aware completer bound to this `Falyx` instance.
        """
        return FalyxCompleter(self)

    def _get_validator_error_message(self) -> str:
        """Build the validation error message shown by the prompt session.

        The message lists all currently visible entry keys and aliases that may be
        invoked from the current namespace.

        Returns:
            str: User-facing validation error text.
        """
        visible = self._iter_visible_entries(
            include_help=True,
            include_history=True,
            include_exit=True,
        )
        keys = {entry.key.upper() for entry in visible}
        for entry in visible:
            for alias in entry.aliases:
                keys.add(alias.upper())

        commands_str = ", ".join(sorted(keys))

        message_lines = ["Invalid input. Available keys:"]
        if keys:
            message_lines.append(f"  Commands: {commands_str}")

        error_message = " ".join(message_lines)
        return error_message

    def _invalidate_prompt_session_cache(self):
        """Drop any cached prompt session so UI changes take effect.

        This is used when bottom-bar configuration or other prompt-session state
        changes and a fresh `PromptSession` must be built on next access.
        """
        if hasattr(self, "prompt_session"):
            del self.prompt_session
        self._prompt_session = None

    @property
    def bottom_bar(self) -> BottomBar | str | Callable[[], Any] | None:
        """Return the configured bottom-bar definition for menu mode."""
        return self._bottom_bar

    @bottom_bar.setter
    def bottom_bar(self, bottom_bar: BottomBar | str | Callable[[], Any] | None) -> None:
        """Install or normalize the bottom-bar configuration.

        `None` produces a default `BottomBar`. A `BottomBar` instance is rebound to
        this namespace's key bindings. Strings and callables are stored directly as
        alternate toolbar renderers.

        Args:
            bottom_bar (BottomBar | str | Callable[[], Any] | None): Toolbar
                configuration to install.

        Raises:
            FalyxError: If the value is not a supported bottom-bar type.
        """
        if bottom_bar is None:
            self._bottom_bar = BottomBar(self.columns, self.key_bindings)
        elif isinstance(bottom_bar, BottomBar):
            bottom_bar.key_bindings = self.key_bindings
            self._bottom_bar = bottom_bar
        elif isinstance(bottom_bar, str) or callable(bottom_bar):
            self._bottom_bar = bottom_bar
        else:
            raise FalyxError(
                "bottom_bar must be a string, callable, None, or BottomBar instance."
            )
        self._invalidate_prompt_session_cache()

    def _get_bottom_bar_render(self) -> Callable[[], Any] | str | None:
        """Return the actual toolbar renderer used by the prompt session.

        Returns:
            Callable[[], Any] | str | None: Render callable, static toolbar string,
            or `None` when no toolbar should be shown.
        """
        if isinstance(self.bottom_bar, BottomBar) and self.bottom_bar.has_items:
            return self.bottom_bar.render
        elif callable(self.bottom_bar):
            return self.bottom_bar
        elif isinstance(self.bottom_bar, str):
            return self.bottom_bar
        return None

    @cached_property
    def prompt_session(self) -> PromptSession:
        """Create and cache the interactive prompt session.

        The prompt session wires together completion, validation, history,
        bottom-toolbar rendering, placeholder content, and quit behavior for menu
        mode.

        Returns:
            PromptSession: Configured prompt session for interactive input.
        """
        if self._prompt_session is None:
            placeholder = self.build_placeholder_menu()
            self._prompt_session = PromptSession(
                message=self.prompt,
                history=self.history,
                multiline=False,
                completer=self._get_completer(),
                complete_style=CompleteStyle.COLUMN,
                validator=CommandValidator(self, self._get_validator_error_message()),
                bottom_toolbar=self._get_bottom_bar_render(),
                key_bindings=self.key_bindings,
                validate_while_typing=True,
                interrupt_exception=QuitSignal,
                eof_exception=QuitSignal,
                placeholder=placeholder if self.show_placeholder_menu else None,
            )
        return self._prompt_session

    def register_all_hooks(self, hook_type: HookType, hooks: Hook | list[Hook]) -> None:
        """Register a hook across the namespace and all nested actions.

        Hooks are attached to the application hook manager, every registered
        command, and any nested `BaseAction` or nested `Falyx` runtime reachable
        through command actions.

        Args:
            hook_type (HookType): Lifecycle slot to register against.
            hooks (Hook | list[Hook]): Single hook or list of hooks to apply recursively.

        Raises:
            InvalidHookError: If any supplied hook is not callable.
        """
        hook_list = hooks if isinstance(hooks, list) else [hooks]
        for hook in hook_list:
            if not callable(hook):
                raise InvalidHookError("hooks must be a callable.")
            self.hooks.register(hook_type, hook)
            for command in self.commands.values():
                command.hooks.register(hook_type, hook)
                if isinstance(command.action, Falyx):
                    command.action.register_all_hooks(hook_type, hook)
                if isinstance(command.action, BaseAction):
                    command.action.register_hooks_recursively(hook_type, hook)

    def register_all_with_debug_hooks(self) -> None:
        """Install the standard debug hook set across all commands and actions."""
        self.register_all_hooks(HookType.BEFORE, log_before)
        self.register_all_hooks(HookType.ON_SUCCESS, log_success)
        self.register_all_hooks(HookType.ON_ERROR, log_error)
        self.register_all_hooks(HookType.AFTER, log_after)

    def _validate_command_aliases(self, key: str, aliases: list[str] | None) -> None:
        """Validate that a new command or namespace identifier set is unique.

        Validation is case-insensitive and checks the proposed key and aliases
        against existing commands, builtins, history, and exit entries.

        Args:
            key (str): Proposed primary key.
            aliases (list[str] | None): Proposed aliases for the same entry.

        Raises:
            CommandAlreadyExistsError: If duplicates or collisions are found.
        """
        key = key.upper()
        aliases = [alias.upper() for alias in (aliases or [])]

        if len(set(aliases)) != len(aliases):
            raise CommandAlreadyExistsError("duplicate aliases provided.")

        if key in aliases:
            raise CommandAlreadyExistsError("command key cannot also be an alias.")

        existing_names = set()

        def collect_names(command: Command):
            existing_names.add(command.key.upper())
            existing_names.update(alias.upper() for alias in command.aliases)

        for command in self.commands.values():
            collect_names(command)

        for command in self.builtins.values():
            collect_names(command)

        collect_names(self.exit_command)

        if self.history_command:
            collect_names(self.history_command)

        new_names = {key, *aliases}

        collisions = new_names.intersection(existing_names)

        if collisions:
            raise CommandAlreadyExistsError(
                f"command identifiers {sorted(collisions)} already exist."
            )

    def update_exit_command(
        self,
        key: str = "X",
        description: str = "Exit",
        aliases: list[str] | None = None,
        action: Callable[..., Any] | None = None,
        style: str = OneColors.DARK_RED,
        confirm: bool = False,
        confirm_message: str = "Are you sure?",
        help_text: str = "Exit the program.",
    ) -> None:
        """Replace the namespace exit command with a custom one.

        This is commonly used by submenus to swap the default exit behavior for a
        back-navigation command.

        Args:
            key (str): New command key.
            description (str): User-facing description.
            aliases (list[str] | None): Optional aliases for the exit command.
            action (Callable[..., Any] | None): Optional callable to execute. Defaults to raising `QuitSignal`.
            style (str): Rich style used for menu/help rendering.
            confirm (bool): Whether the command should require confirmation.
            confirm_message (str): Confirmation prompt text.
            help_text (str): Help text shown in command listings and help output.

        Raises:
            InvalidActionError: If the supplied action is not callable.
        """
        self._validate_command_aliases(key, aliases)
        action = action or SignalAction(description, QuitSignal())
        if not callable(action):
            raise InvalidActionError("action must be a callable.")
        self.exit_command = Command(
            key=key,
            description=description,
            aliases=aliases if aliases else self.exit_command.aliases,
            action=action,
            style=style,
            confirm=confirm,
            confirm_message=confirm_message,
            ignore_in_history=True,
            options_manager=self.options,
            program=self.program,
            help_text=help_text,
        )
        if self.exit_command.arg_parser:
            self.exit_command.arg_parser.add_tldr_examples([("", help_text)])

    def add_submenu(
        self,
        key: str,
        description: str,
        submenu: Falyx,
        *,
        style: str | None = None,
        aliases: list[str] | None = None,
        help_text: str = "",
        hidden: bool = False,
    ) -> None:
        """Register a nested `Falyx` instance as a namespace entry.

        The submenu becomes part of routing, completion, and help output in the
        current namespace. When the submenu still uses the default exit command, it
        is converted to a back command automatically.

        Args:
            key (str): Namespace key used to enter the submenu.
            description (str): User-facing namespace description.
            submenu (Falyx): Nested `Falyx` instance to register.
            style (StyleType | None): Optional style override for the namespace entry.
            aliases (list[str] | None): Optional aliases for the namespace.
            help_text (str): Optional help text for namespace listings.
            hidden (bool): Where the namespace should be omitted from visible menus and
                help listings.

        Raises:
            NotAFalyxError: If `submenu` is not a `Falyx` instance.
        """
        if not isinstance(submenu, Falyx):
            raise NotAFalyxError("submenu must be an instance of Falyx.")

        self._validate_command_aliases(key, aliases)

        entry = FalyxNamespace(
            key=key,
            description=description,
            namespace=submenu,
            aliases=aliases or [],
            help_text=help_text or f"Open the {description} namespace.",
            style=style or submenu.program_style,
            hidden=hidden,
        )

        self.namespaces[key] = entry

        if submenu.exit_command.key == "X":
            submenu.update_exit_command(
                key="B",
                description="Back",
                aliases=["BACK"],
                help_text="Go back to the previous menu.",
            )

    def add_commands(self, commands: list[Command] | list[dict]) -> None:
        """Register multiple commands from instances or config dictionaries.

        Args:
            commands (list[Command] | list[dict]): Sequence of `Command` objects or
                `add_command()` keyword dictionaries.

        Raises:
            FalyxError: If an element is neither a `Command` nor a configuration
                dictionary.
        """
        for command in commands:
            if isinstance(command, dict):
                self.add_command(**command)
            elif isinstance(command, Command):
                self.add_command_from_command(command)
            else:
                raise FalyxError(
                    "command must be a dictionary or an instance of Command."
                )

    def add_command_from_command(self, command: Command) -> None:
        """Register an already-built `Command` object.

        Args:
            command (Command): Preconstructed command to add to this namespace.

        Raises:
            FalyxError: If `command` is not a `Command`.
        """
        if not isinstance(command, Command):
            raise FalyxError("command must be an instance of Command.")
        self._validate_command_aliases(command.key, command.aliases)
        self.commands[command.key] = command
        _ = self._entry_map

    def add_command(
        self,
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
        custom_usage: Callable[[], str | None] | None = None,
        auto_args: bool = True,
        arg_metadata: dict[str, str | dict[str, Any]] | None = None,
        simple_help_signature: bool = False,
        ignore_in_history: bool = False,
    ) -> Command:
        """Build and register a new command in the current namespace.

        This is the main command-registration API for `Falyx`. It forwards the
        supplied configuration to `Command.build()`, injects shared runtime state,
        validates identifier uniqueness, and stores the resulting command.

        Args:
            key (str): Primary command key.
            description (str): User-facing command description.
            action (BaseAction | Callable[..., Any]): Underlying action or callable executed by the command.
            args (tuple): Static positional arguments bound to the command.
            kwargs (dict[str, Any] | None): Static keyword arguments bound to the command.
            hidden (bool): Whether the command should be omitted from menu/help listings.
            aliases (list[str] | None): Optional alternate invocation names.
            help_text (str): Short help text shown in listings.
            help_epilog (str): Extended help text shown in command help.
            style (str): Rich style used for display.
            confirm (bool): Whether confirmation should be required before execution.
            confirm_message (str): Confirmation prompt text.
            preview_before_confirm (bool): Whether preview should run before confirmation.
            spinner (bool): Whether spinner hooks should be enabled.
            spinner_message (str): Spinner label.
            spinner_type (str): Rich spinner preset name.
            spinner_style (str): Rich style for spinner output.
            spinner_speed (float): Spinner speed multiplier.
            hooks (HookManager | None): Optional command hook manager.
            before_hooks (list[Callable] | None): Optional before hooks.
            success_hooks (list[Callable] | None): Optional success hooks.
            error_hooks (list[Callable] | None): Optional error hooks.
            after_hooks (list[Callable] | None): Optional after hooks.
            teardown_hooks (list[Callable] | None): Optional teardown hooks.
            tags (list[str] | None): Optional tag labels for grouping and help filtering.
            logging_hooks (bool): Whether debug hooks should be enabled.
            retry (bool): Whether retry behavior should be enabled.
            retry_all (bool): Whether retry should be applied recursively to nested actions.
            retry_policy (RetryPolicy | None): Retry policy override.
            arg_parser (CommandArgumentParser | None): Optional explicit command argument parser.
            arguments (list[dict[str, Any]] | None): Optional declarative argument definitions.
            argument_config (Callable[[CommandArgumentParser], None] | None): Optional callback that populates the parser.
            execution_options (list[ExecutionOption | str] | None): Optional execution-level options to enable.
            custom_parser (ArgParserProtocol | None): Optional parser override for full custom argument parsing.
            custom_help (Callable[[], str | None] | None): Optional custom help renderer.
            custom_tldr (Callable[[], str | None] | None): Optional custom TLDR renderer.
            custom_usage (Callable[[], str | None] | None): Optional custom usage renderer.
            auto_args (bool): Whether argument inference should run automatically.
            arg_metadata (dict[str, str | dict[str, Any]] | None): Optional metadata used during argument inference.
            simple_help_signature (bool): Whether command listings should use compact help.
            ignore_in_history (bool): Whether this command should be ignored by history-aware
                result tracking.

        Returns:
            Command: The newly built and registered command.
        """
        self._validate_command_aliases(key, aliases)

        command = Command.build(
            key=key,
            description=description,
            action=action,
            args=args,
            kwargs=kwargs,
            hidden=hidden,
            aliases=aliases,
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
            hooks=hooks,
            before_hooks=before_hooks,
            success_hooks=success_hooks,
            error_hooks=error_hooks,
            after_hooks=after_hooks,
            teardown_hooks=teardown_hooks,
            tags=tags,
            logging_hooks=logging_hooks,
            retry=retry,
            retry_all=retry_all,
            retry_policy=retry_policy,
            arg_parser=arg_parser,
            arguments=arguments,
            argument_config=argument_config,
            custom_parser=custom_parser,
            custom_help=custom_help,
            custom_tldr=custom_tldr,
            custom_usage=custom_usage,
            execution_options=execution_options,
            auto_args=auto_args,
            arg_metadata=arg_metadata,
            simple_help_signature=simple_help_signature,
            options_manager=self.options,
            ignore_in_history=ignore_in_history,
            program=self.program,
        )

        self.commands[key] = command
        _ = self._entry_map
        return command

    def _get_bottom_row(self) -> list[str]:
        """Build the special bottom-row entries for menu tables.

        Returns:
            list[str]: Rendered help, history, and exit command labels.
        """
        bottom_row = []
        if self.help_command:
            bottom_row.append(
                f"[{self.help_command.key}] [{self.help_command.style}]"
                f"{self.help_command.description}[/]"
            )
        if self.history_command:
            bottom_row.append(
                f"[{self.history_command.key}] [{self.history_command.style}]"
                f"{self.history_command.description}[/]"
            )
        bottom_row.append(
            f"[{self.exit_command.key}] [{self.exit_command.style}]"
            f"{self.exit_command.description}[/]"
        )
        return bottom_row

    def _iter_visible_entries(
        self,
        *,
        include_builtins: bool = False,
        include_help: bool = False,
        include_history: bool = False,
        include_exit: bool = False,
    ) -> list[Command | FalyxNamespace]:
        """Collect visible entries for menu or validation message use.

        Args:
            include_builtins (bool): Whether normal builtin commands should be included.
            include_help (bool): Whether the help command should be appended.
            include_history (bool): Whether the history command should be appended.
            include_exit (bool): Whether the exit command should be appended.

        Returns:
            list[Command | FalyxNamespace]: Visible entries in display order.
        """
        visible: list[Command | FalyxNamespace] = []
        visible.extend([cmd for cmd in self.commands.values() if not cmd.hidden])
        visible.extend([ns for ns in self.namespaces.values() if not ns.hidden])
        if include_builtins:
            visible.extend([cmd for cmd in self.builtins.values() if not cmd.hidden])
        if include_help:
            visible.append(self.help_command)
        if include_history and self.history_command:
            visible.append(self.history_command)
        if include_exit:
            visible.append(self.exit_command)
        return visible

    def build_default_table(self) -> Table:
        """Build the standard Rich table used for menu display.

        Returns:
            Table: Default menu table for the current namespace.
        """
        table = Table(
            title=self.title,
            show_header=False,
            box=box.SIMPLE,
            title_style=self.title_style,
            caption=self.caption,
            caption_style=self.caption_style,
        )
        visible = self._iter_visible_entries()
        for chunk in chunks(visible, self.columns):
            row = []
            for entry in chunk:
                escaped_key = escape(f"[{entry.key}]")
                row.append(f"{escaped_key} [{entry.style}]{entry.description}")
            table.add_row(*row)
        bottom_row = self._get_bottom_row()
        for row in chunks(bottom_row, self.columns):
            table.add_row(*row)
        return table

    def build_placeholder_menu(self) -> StyleAndTextTuples:
        """Build placeholder text for the interactive prompt.

        The placeholder summarizes visible commands and special bottom-row entries
        and is used when `show_placeholder_menu` is enabled.

        Returns:
            StyleAndTextTuples: Prompt Toolkit-compatible formatted placeholder.
        """
        visible_commands = [item for item in self.commands.items() if not item[1].hidden]
        if not visible_commands:
            return [("", "")]

        placeholder: list[str] = []
        for key, command in visible_commands:
            placeholder.append(f"[{key}] [{command.style}]{command.description}[/]")
        for command_str in self._get_bottom_row():
            placeholder.append(command_str)

        return rich_text_to_prompt_text(" ".join(placeholder))

    @property
    def table(self) -> Table:
        """Return the active menu table for this namespace.

        When `custom_table` is callable, it is invoked and must return a Rich
        `Table`. When `custom_table` is already a `Table`, that instance is reused.
        Otherwise the default menu table is built.

        Returns:
            Table: Table used by menu rendering.

        Raises:
            FalyxError: If a custom table factory returns a non-`Table` value.
        """
        if callable(self.custom_table):
            custom_table = self.custom_table(self)
            if not isinstance(custom_table, Table):
                raise FalyxError(
                    "custom_table must return an instance of rich.table.Table."
                )
            return custom_table
        elif isinstance(self.custom_table, Table):
            return self.custom_table
        else:
            return self.build_default_table()

    def resolve_entry(
        self,
        token: str,
    ) -> tuple[Command | FalyxNamespace | None, list[str]]:
        """Resolve a token to a command or namespace entry.

        Resolution is case-insensitive and proceeds in three stages:

        1. Exact identifier match
        2. Unique prefix match
        3. Close-match suggestion lookup

        Args:
            token (str): Raw user token to resolve.

        Returns:
            tuple[Command | FalyxNamespace | None, list[str]]: Resolved entry, if
            any, plus suggestion strings when resolution fails.
        """
        normalized = token.upper().strip()

        # exact match
        if normalized in self._entry_map:
            return self._entry_map[normalized], []

        # unique prefix match
        prefix_matches = []
        seen = set()
        for key, entry in self._entry_map.items():
            if key.startswith(normalized) and id(entry) not in seen:
                prefix_matches.append(entry)
                seen.add(id(entry))

        if len(prefix_matches) == 1:
            return prefix_matches[0], []

        # close match suggestions
        suggestions = get_close_matches(
            normalized, list(self._entry_map.keys()), n=3, cutoff=0.7
        )
        return None, suggestions

    async def prepare_route(
        self,
        raw_arguments: list[str] | str,
        *,
        mode: FalyxMode | None = None,
        from_validate: bool = False,
    ) -> tuple[RouteResult, tuple, dict[str, Any], dict[str, Any]]:
        """Tokenize input, resolve a route, and parse leaf-command arguments.

        This is the main preparation boundary between raw user input and executable
        command dispatch. It:

        - tokenizes shell-style input
        - detects preview-prefixed commands
        - creates an initial `InvocationContext`
        - resolves a `RouteResult` through namespace routing
        - delegates leaf argument parsing to the resolved command when appropriate

        Args:
            raw_arguments (list[str] | str): Raw argv-style input as a string or token list.
            mode (FalyxMode | None): Optional mode override for the initial invocation context.
            from_validate (bool): Whether errors should be surfaced as prompt validation
                errors instead of normal runtime output.

        Returns:
            tuple[RouteResult, tuple, dict[str, Any], dict[str, Any]]:
                Resolved route, positional args, keyword args, and execution args.

        Raises:
            ValidationError: If `from_validate` is `True` and tokenization or argument parsing fails.
            CommandArgumentError: If `from_validate` is `False` and argument parsing fails
        """
        args: tuple = ()
        kwargs: dict[str, Any] = {}
        execution_args: dict[str, Any] = {}
        if isinstance(raw_arguments, str):
            try:
                tokens = shlex.split(raw_arguments)
            except ValueError as error:
                if from_validate:
                    raise ValidationError(
                        cursor_position=len(raw_arguments), message=f"{error}"
                    ) from error
                raise UsageError(str(error)) from error
        elif isinstance(raw_arguments, list):
            tokens = raw_arguments
        else:
            if from_validate:
                assert (
                    False
                ), "Validator can only pass a string or list of strings as raw_arguments."
            raise UsageError(
                "raw_arguments must be a string or list of strings."
            ) from TypeError("invalid type for raw_arguments")

        is_preview = False
        if tokens and tokens[0].startswith("?") and len(tokens[0]) > 1:
            is_preview = True
            tokens[0] = tokens[0][1:]

        context = InvocationContext(
            program=self.program,
            program_style=self.program_style,
            typed_path=[],
            mode=mode or self.options.get("mode"),
            is_preview=is_preview,
        )

        try:
            route = await self.resolve_route(
                tokens,
                invocation_context=context,
                is_preview=is_preview,
            )
        except FalyxError as error:
            if from_validate:
                hint = f" hint: {error.hint}" if error.hint else ""
                raise ValidationError(
                    cursor_position=len(raw_arguments), message=f"{error}{hint}"
                ) from error
            raise

        if route.is_preview:
            return route, args, kwargs, execution_args

        if route.kind is RouteKind.COMMAND:
            assert route.command is not None
            try:
                args, kwargs, execution_args = await route.command.resolve_args(
                    route.leaf_argv,
                    from_validate=from_validate,
                    invocation_context=route.context,
                )
            except CommandArgumentError as error:
                if from_validate:
                    hint = f" hint: {error.hint}" if error.hint else ""
                    raise ValidationError(
                        cursor_position=len(raw_arguments), message=f"{error}{hint}"
                    ) from error
                else:
                    raise error
            except HelpSignal:
                if not from_validate:
                    raise
            return route, args, kwargs, execution_args

        return route, args, kwargs, execution_args

    async def _render_unknown_route(
        self,
        route: RouteResult,
    ) -> None:
        """Render help plus suggestions for an unresolved route.

        Args:
            route (RouteResult): Unknown route returned by namespace resolution.

        Raises:
            FalyxError: If the route is a preview route, which cannot be rendered.
            EntryNotFoundError: If the route is unknown and cannot be resolved.
        """
        if route.kind is RouteKind.NAMESPACE_MENU:
            raise FalyxError("preview mode is only supported for commands.")
        else:
            raise EntryNotFoundError(
                unknown_name=route.current_head,
                suggestions=route.suggestions,
            )

    async def _dispatch_route(
        self,
        route: RouteResult,
        *,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
        execution_args: dict[str, Any] | None = None,
        raise_on_error: bool = False,
        wrap_errors: bool = True,
        summary_last_result: bool = False,
    ) -> Any | None:
        """Dispatch a prepared route to help rendering, menu flow, or execution.

        This method is the final route-handling stage after preparation. It knows
        how to handle namespace menus, namespace help, namespace TLDR, unknown
        routes, preview routes, and normal leaf-command execution.

        Args:
            route (RouteResult): Prepared route to dispatch.
            args (tuple): Positional arguments prepared for a leaf command.
            kwargs (dict[str, Any] | None): Keyword arguments prepared for a leaf command.
            execution_args (dict[str, Any] | None): Execution-only arguments such as
                confirmation or retry overrides.
            raise_on_error (bool): Whether executor errors should be re-raised.
            wrap_errors (bool): Whether executor errors should be wrapped as `FalyxError`.
            summary_last_result (bool): Whether summary output should only have the last
                result when supported.

        Returns:
            Any | None: Command result for executed leaf commands, otherwise `None`.

        Raises:
            FalyxError: If the route is invalid for preview or if execution fails and
                `wrap_errors` is `True`.
            Exception: If execution fails and `raise_on_error` is `True` and
                `wrap_errors` is `False`.
            EntryNotFoundError: If the route is unknown and cannot be resolved.
            KeyboardInterrupt: If execution is interrupted by the user and `wrap_errors`
                is `False`.
            EOFError: If execution receives an unexpected end of input and `wrap_errors`
                is `False`.
        """
        if route.is_preview:
            if route.kind is RouteKind.COMMAND and route.command:
                logger.info("preview command '%s' selected.", route.command.key)
                await route.command.preview()
            else:
                logger.info("preview route selected with no command.")
                await self._render_unknown_route(route)
            return None

        if route.kind is RouteKind.NAMESPACE_MENU:
            await route.namespace.menu()
            return None

        if route.kind is RouteKind.NAMESPACE_HELP:
            await route.namespace.render_namespace_help(route.context)
            return None

        if route.kind is RouteKind.NAMESPACE_TLDR:
            await route.namespace.render_namespace_help(route.context, tldr=True)
            return None

        if route.kind is RouteKind.UNKNOWN:
            await self._render_unknown_route(route)
            return None

        if route.kind is RouteKind.COMMAND:
            if not route.command:
                raise FalyxError("invalid route: command expected but not found.")

            command = route.command

            if command is route.namespace.help_command:
                kwargs = kwargs or {}
                kwargs["invocation_context"] = route.context

            logger.debug(
                "Executing command '%s' with args=%s, kwargs=%s, execution_args=%s",
                route.command.description,
                args,
                kwargs,
                execution_args,
            )
            return await self._executor.execute(
                command=route.command,
                args=args,
                kwargs=kwargs or {},
                execution_args=execution_args or {},
                raise_on_error=raise_on_error,
                wrap_errors=wrap_errors,
                summary_last_result=summary_last_result,
            )

    async def execute_command(
        self,
        raw_arguments: list[str] | str,
        *,
        raise_on_error: bool = False,
        wrap_errors: bool = True,
        summary_last_result: bool = False,
        mode: FalyxMode = FalyxMode.MENU,
    ) -> Any | None:
        """Execute a command from a raw CLI-style input string.

        This method resolves the requested command from `raw_arguments`, parses any
        command-specific arguments, handles preview and exit behavior, and delegates
        actual execution to the shared `CommandExecutor`.

        Behavior:
            - Resolves the command and its parsed `args`, `kwargs`, and
            `execution_args` via `prepare_route()`.
            - Returns `None` when help output is triggered, argument parsing fails,
            the command cannot be found, or preview mode is requested.
            - For normal execution, forwards the resolved command and execution
            options to `_executor.execute()`.

        Args:
            raw_arguments (str): Raw command input string, including the command name
                and any CLI-style arguments (for example, ``"deploy --region us-east"``).
            raise_on_error (bool): Whether execution errors raised by the underlying
                executor should be re-raised to the caller.
            wrap_errors (bool): Whether execution errors should be wrapped in a
                `FalyxError` by the underlying executor before being raised.
            summary_last_result (bool): Whether summary output should include the last
                result when execution summary reporting is requested.
            mode (FalyxMode): Runtime mode used while preparing the route.

        Returns:
            Any | None: The command result returned by the underlying executor, or
            `None` if execution does not occur because help was shown, preview mode
            was used, parsing failed, or the command was not found.

        Raises:
            QuitSignal: If the resolved command is the configured exit command.
            FalyxError: If the route is invalid for preview or if execution fails and
                `wrap_errors` is `True`.
            Exception: If execution fails and `raise_on_error` is `True` and
                `wrap_errors` is `False`.
            KeyboardInterrupt: If execution is interrupted by the user and
                `wrap_errors` is `False`.
            EOFError: If execution receives an unexpected end of input and
                `wrap_errors` is `False`.

        Notes:
            - This method is the primary programmatic entrypoint for executing a
                command from a raw input string outside the interactive menu loop.
            - One of the flags `raise_on_error` or `wrap_errors` must be `True` to
                ensure that errors are properly handled.
        """
        if not (raise_on_error or wrap_errors):
            raise FalyxError(
                "Falyx.execute_command() requires either raise_on_error=True "
                "or wrap_errors=True."
            )
        route, args, kwargs, execution_args = await self.prepare_route(
            raw_arguments, mode=mode
        )

        assert route is not None, "prepare_route should never return None."

        return await self._dispatch_route(
            route=route,
            args=args,
            kwargs=kwargs,
            execution_args=execution_args,
            raise_on_error=raise_on_error,
            wrap_errors=wrap_errors,
            summary_last_result=summary_last_result,
        )

    def resolve_completion_route(
        self,
        committed_tokens: list[str],
        *,
        stub: str,
        cursor_at_end_of_token: bool,
        invocation_context: InvocationContext,
        is_preview: bool = False,
    ) -> CompletionRoute:
        """Resolve partial input for autocompletion.

        Unlike full routing, completion routing tolerates incomplete trailing input.
        It stops at the first point where completion must either suggest namespace
        entries or delegate the remaining input to a leaf command's argument parser.

        Args:
            committed_tokens (list[str]): Tokens fully committed before the active stub.
            stub (str): Current token fragment under the cursor.
            cursor_at_end_of_token (bool): Whether the cursor sits at a token boundary.
            invocation_context (InvocationContext): Current routed invocation context.
            is_preview (bool): Whether the input is preview-prefixed.

        Returns:
            CompletionRoute: Partial route used by the completer.
        """
        namespace = self
        route_context = invocation_context
        remaining = list(committed_tokens)

        while remaining:
            head = remaining.pop(0)
            entry, _ = namespace.resolve_entry(head)

            if entry is None:
                # Still routing namespace entries; could not resolve this token.
                # Let the completer suggest entries or namespace-level flags.
                return CompletionRoute(
                    namespace=namespace,
                    context=route_context,
                    command=None,
                    leaf_argv=[],
                    stub=head if not remaining else stub,
                    cursor_at_end_of_token=cursor_at_end_of_token,
                    expecting_entry=True,
                    is_preview=is_preview,
                )

            route_context = route_context.with_path_segment(head, style=entry.style)

            if isinstance(entry, FalyxNamespace):
                namespace = entry.namespace
                continue

            # Leaf command found: everything after this belongs to CAP unchanged.
            return CompletionRoute(
                namespace=namespace,
                context=route_context,
                command=entry,
                leaf_argv=remaining,
                stub=stub,
                cursor_at_end_of_token=cursor_at_end_of_token,
                expecting_entry=False,
                is_preview=is_preview,
            )

        # No committed leaf yet: next token should be a namespace entry.
        return CompletionRoute(
            namespace=namespace,
            context=route_context,
            command=None,
            leaf_argv=[],
            stub=stub,
            cursor_at_end_of_token=cursor_at_end_of_token,
            expecting_entry=True,
            is_preview=is_preview,
        )

    async def resolve_route(
        self,
        tokens: list[str],
        *,
        invocation_context: InvocationContext,
        is_preview: bool = False,
    ) -> RouteResult:
        """Resolve an invocation path across namespaces until a leaf boundary.

        Routing is recursive and namespace-aware. It stops when one of the
        following occurs:

        - no tokens remain, targeting the current namespace menu
        - a namespace-level help or TLDR flag is encountered
        - an unknown token is found
        - a leaf command is reached

        Args:
            tokens (list[str]): Remaining tokens to route.
            invocation_context (InvocationContext): Routed context accumulated so far.
            is_preview (bool): Whether the input is preview-prefixed.
        Returns:
            RouteResult: Final routed result for the supplied token path.
        """
        # 1. Namespace-level parsing for help/tldr flags and root/session options
        parse_result = self.parser.parse_args(tokens)
        self.parser.apply_to_options(parse_result, self.options)
        tokens = parse_result.remaining_argv

        # 2. Help or TLDR requested for this namespace
        if parse_result.help:
            return RouteResult(
                kind=RouteKind.NAMESPACE_HELP,
                namespace=self,
                context=invocation_context,
                current_head=parse_result.current_head,
                is_preview=is_preview,
            )
        if parse_result.tldr:
            return RouteResult(
                kind=RouteKind.NAMESPACE_TLDR,
                namespace=self,
                context=invocation_context,
                current_head=parse_result.current_head,
                is_preview=is_preview,
            )

        # 3. No more tokens -> this namespace itself was targeted
        if not tokens:
            return RouteResult(
                kind=RouteKind.NAMESPACE_MENU,
                namespace=self,
                context=invocation_context,
                is_preview=is_preview,
            )

        head, *tail = tokens

        # 4. Resolve the next entry in this namespace
        entry, suggestions = self.resolve_entry(head)
        if entry is None:
            return RouteResult(
                kind=RouteKind.UNKNOWN,
                namespace=self,
                context=invocation_context,
                current_head=head,
                suggestions=suggestions,
                is_preview=is_preview,
            )

        route_context = invocation_context.with_path_segment(head, style=entry.style)

        # 5. Namespace entry -> recurse with remaining tokens
        if isinstance(entry, FalyxNamespace):
            return await entry.namespace.resolve_route(
                tail, invocation_context=route_context, is_preview=is_preview
            )

        # 6. Leaf command -> stop routing; leave tail untouched for leaf parser
        return RouteResult(
            kind=RouteKind.COMMAND,
            namespace=self,
            context=route_context,
            command=entry,
            leaf_argv=tail,
            current_head=head,
            is_preview=is_preview,
        )

    async def _process_command(self) -> None:
        """Read one prompt input from the interactive session and execute it.

        This helper refreshes the Prompt Toolkit app, collects raw input from the
        cached prompt session, and forwards that input to `execute_command()`.
        """
        app = get_app()
        await asyncio.sleep(0.1)
        app.invalidate()
        with patch_stdout(raw=True):
            raw_arguments = await self.prompt_session.prompt_async()
        try:
            await self.execute_command(
                raw_arguments,
                raise_on_error=False,
                wrap_errors=True,
                summary_last_result=True,
            )
        except FalyxError as error:
            print_error(message=error)

    async def menu(self) -> None:
        """Run the interactive menu loop for this namespace.

        The menu loop renders the current table view, reads commands from the prompt
        session, handles navigation and cancellation signals, and prints optional
        welcome and exit messages.
        """
        logger.info("Starting menu: %s", self.title)
        self.options.set("mode", FalyxMode.MENU)
        if self.welcome_message:
            self.console.print(self.welcome_message)
        try:
            while True:
                if not self.options.get("hide_menu_table", self._hide_menu_table):
                    if callable(self.render_menu):
                        self.render_menu(self)
                    else:
                        self.console.print(self.table, justify="center")
                try:
                    await self._process_command()
                except (EOFError, KeyboardInterrupt):
                    logger.info("EOF or KeyboardInterrupt. Exiting menu.")
                    break
                except HelpSignal:
                    logger.info("[HelpSignal]. <- Returning to the menu.")
                except QuitSignal:
                    logger.info("[QuitSignal]. <- Exiting menu.")
                    break
                except BackSignal:
                    logger.info("[BackSignal]. <- Returning to the menu.")
                except CancelSignal:
                    logger.info("[CancelSignal]. <- Returning to the menu.")
                except asyncio.CancelledError:
                    logger.info("[asyncio.CancelledError]. <- Returning to the menu.")
        finally:
            logger.info("Exiting menu: %s", self.title)
            if self.exit_message:
                self.console.print(self.exit_message)

    def _apply_parse_result(self, result: ParseResult) -> None:
        """Apply parsed root/session options to runtime state.

        This updates the active mode, logging verbosity, debug-hook registration,
        and prompt behavior based on the root parse result.

        Args:
            result (ParseResult): Parsed root CLI result to apply.
        """
        self.options.set("mode", result.mode)

        if result.verbose:
            logging.getLogger("falyx").setLevel(logging.DEBUG)
            self.options.set("verbose", True)
        else:
            self.options.set("verbose", False)

        if result.debug_hooks:
            self.options.set("debug_hooks", True)
            self.register_all_with_debug_hooks()
            logger.debug("Enabling global debug hooks for all commands")
        else:
            self.options.set("debug_hooks", False)

        if result.never_prompt:
            self.options.set("never_prompt", True)

    async def run(self, always_start_menu: bool = False) -> None:
        """Execute the Falyx application using CLI-driven dispatch.

        This method is the primary entrypoint for Falyx applications.

        - parses root CLI flags using `FalyxParser`
        - optionally invokes a post-parse callback
        - applies session/runtime options
        - renders help immediately when requested
        - prepares and dispatches the routed command
        - exits with CLI-appropriate status codes
        - optionally falls through to interactive menu mode

        Args:
            always_start_menu (bool): Whether to enter menu mode after a successful
                command dispatch when the route itself does not already target help
                or a namespace menu.

        Raises:
            FalyxError:
                If command execution fails.
            SystemExit:
                Terminates the process with an appropriate exit code based on mode.

        Notes:
            - Most CLI execution paths terminate via `sys.exit()`
            - Interactive mode continues via `menu()`
            - Execution options are applied in a scoped "execution" namespace

        Example:
            ```
            >>> import asyncio
            >>> flx = Falyx()
            >>> asyncio.run(flx.run())
            ```
        """
        if not sys.argv[1:] and not self.default_to_menu and not always_start_menu:
            await self.render_help()
            sys.exit(0)

        try:
            route, args, kwargs, execution_args = await self.prepare_route(
                raw_arguments=sys.argv[1:],
            )
        except UsageError as error:
            if error.show_short_usage:
                self.render_usage()
            print_error(message=error)
            sys.exit(2)
        except HelpSignal:
            sys.exit(0)

        assert route is not None, "prepare_route should never return None."

        try:
            await self._dispatch_route(
                route=route,
                args=args,
                kwargs=kwargs,
                execution_args=execution_args,
                raise_on_error=False,
                wrap_errors=True,
            )
        except EntryNotFoundError as error:
            await self.render_help()
            print_error(message=error)
            sys.exit(2)
        except (FalyxError, Exception) as error:
            print_error(message=error)
            if self.options.get("verbose"):
                logger.error("Error: %s", error, exc_info=True)
            sys.exit(1)
        except QuitSignal:
            logger.info("[QuitSignal]. <- Exiting run.")
            sys.exit(130)
        except BackSignal:
            logger.info("[BackSignal]. <- Exiting run.")
            sys.exit(1)
        except CancelSignal:
            logger.info("[CancelSignal]. <- Exiting run.")
            sys.exit(1)
        except FlowSignal:
            logger.info("[FlowSignal]. <- Exiting run.")
            sys.exit(1)
        except asyncio.CancelledError:
            logger.info("[asyncio.CancelledError]. <- Exiting run.")
            sys.exit(1)

        if (
            route.kind
            in (
                RouteKind.NAMESPACE_MENU,
                RouteKind.NAMESPACE_TLDR,
                RouteKind.NAMESPACE_HELP,
            )
            or route.command is self.help_command
            or not always_start_menu
        ):
            sys.exit(0)

        await self.menu()
