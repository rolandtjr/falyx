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
from rich.markdown import Markdown
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel
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
from falyx.console import console
from falyx.context import InvocationContext
from falyx.debug import log_after, log_before, log_error, log_success
from falyx.exceptions import (
    CommandAlreadyExistsError,
    CommandArgumentError,
    FalyxError,
    InvalidActionError,
    NotAFalyxError,
)
from falyx.execution_option import ExecutionOption
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.logger import logger
from falyx.mode import FalyxMode
from falyx.namespace import FalyxNamespace
from falyx.options_manager import OptionsManager
from falyx.parser import CommandArgumentParser, FalyxParser, RootParseResult
from falyx.parser.parser_types import FalyxTLDRExample, FalyxTLDRInput
from falyx.prompt_utils import rich_text_to_prompt_text
from falyx.protocols import ArgParserProtocol
from falyx.retry import RetryPolicy
from falyx.routing import RouteKind, RouteResult
from falyx.signals import BackSignal, CancelSignal, HelpSignal, QuitSignal
from falyx.themes import OneColors
from falyx.utils import CaseInsensitiveDict, chunks, ensure_async
from falyx.validators import CommandValidator
from falyx.version import __version__


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
        title: str | Markdown = "Menu",
        *,
        program: str | None = "falyx",
        usage: str | None = None,
        description: str | None = "Falyx CLI - Run structured async command workflows.",
        epilog: str | None = None,
        version: str = __version__,
        program_style: str = OneColors.BLUE_b,
        usage_style: str = "white",
        description_style: str = OneColors.BLUE,
        epilog_style: str = "white",
        version_style: str = OneColors.BLUE_b,
        prompt: str | StyleAndTextTuples = "> ",
        columns: int = 3,
        bottom_bar: BottomBar | str | Callable[[], Any] | None = None,
        welcome_message: str | Markdown | dict[str, Any] = "",
        exit_message: str | Markdown | dict[str, Any] = "",
        key_bindings: KeyBindings | None = None,
        include_history_command: bool = True,
        never_prompt: bool = False,
        force_confirm: bool = False,
        options: OptionsManager | None = None,
        render_menu: Callable[[Falyx], None] | None = None,
        custom_table: Callable[[Falyx], Table] | Table | None = None,
        hide_menu_table: bool = False,
        show_placeholder_menu: bool = False,
        prompt_history_base_dir: Path = Path.home(),
        enable_prompt_history: bool = False,
        enable_help_tips: bool = True,
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
            title (str | Markdown): Title displayed for the interactive menu or top-level
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
            program_style (str): Rich style used when rendering the program name.
            usage_style (str): Rich style used for rendered usage text.
            description_style (str): Rich style used for the program description.
            epilog_style (str): Rich style used for the help epilog.
            version_style (str): Rich style used for version output and version-related
                rendering.
            prompt (str | StyleAndTextTuples): Prompt text or Prompt Toolkit formatted text
                shown in menu mode.
            columns (int): Default column count used by menu-oriented UI components such as
                the bottom bar.
            bottom_bar (BottomBar | str | Callable[[], Any] | None): Bottom toolbar
                configuration for menu mode. May be a `BottomBar` instance, a static
                string, a callable renderer, or `None` to use the default bottom bar.
            welcome_message (str | Markdown | dict[str, Any]): Optional welcome content
                rendered when entering the interactive menu.
            exit_message (str | Markdown | dict[str, Any]): Optional exit content rendered
                when leaving the interactive menu.
            key_bindings (KeyBindings | None): Optional Prompt Toolkit key bindings for
                menu interaction. If omitted, a default `KeyBindings` object is created.
            include_history_command (bool): Whether to register the built-in history
                command.
            never_prompt (bool): Default session-level value for the `never_prompt`
                runtime option.
            force_confirm (bool): Default session-level value for the `force_confirm`
                runtime option.
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
        self.title: str | Markdown = title
        self.program: str = program or ""
        self.usage: str | None = usage
        self.description: str | None = description
        self.epilog: str | None = epilog
        self.version: str = version
        self.program_style: str = program_style
        self.usage_style: str = usage_style
        self.description_style: str = description_style
        self.epilog_style: str = epilog_style
        self.version_style: str = version_style
        self.prompt: str | StyleAndTextTuples = rich_text_to_prompt_text(prompt)
        self.columns: int = columns
        self.commands: dict[str, Command] = CaseInsensitiveDict()
        self.builtins: dict[str, Command] = CaseInsensitiveDict()
        self.namespaces: dict[str, FalyxNamespace] = CaseInsensitiveDict()
        self.console: Console = console
        self.welcome_message: str | Markdown | dict[str, Any] = welcome_message
        self.exit_message: str | Markdown | dict[str, Any] = exit_message
        self.hooks: HookManager = HookManager()
        self.key_bindings: KeyBindings = key_bindings or KeyBindings()
        self.bottom_bar: BottomBar | str | Callable[[], None] | None = bottom_bar
        self._never_prompt: bool = never_prompt
        self._force_confirm: bool = force_confirm
        self.render_menu: Callable[[Falyx], None] | None = render_menu
        self.custom_table: Callable[[Falyx], Table] | Table | None = custom_table
        self._hide_menu_table: bool = hide_menu_table
        self.show_placeholder_menu: bool = show_placeholder_menu
        self._validate_options(options)
        self._prompt_session: PromptSession | None = None
        self.options.set("mode", FalyxMode.MENU)
        self.exit_command: Command = self._get_exit_command()
        self.history_command: Command | None = (
            self._get_history_command() if include_history_command else None
        )
        self.help_command: Command = self._get_help_command()
        if enable_prompt_history:
            program = (self.program or "falyx").split(".")[0].replace(" ", "_")
            self.history_path: Path = (
                Path(prompt_history_base_dir) / f".{program}_history"
            )
            self.history: FileHistory | None = FileHistory(self.history_path)
        else:
            self.history = None
        self.enable_help_tips = enable_help_tips
        self._tldr_examples: list[FalyxTLDRExample] = []
        self._register_default_builtins()
        self._register_options()
        self._executor = CommandExecutor(
            options=self.options,
            hooks=self.hooks,
            console=self.console,
        )

    def _print_suggestions_message(
        self,
        key: str,
        suggestions: list[str],
        message_context: str = "",
    ) -> None:
        """Render an unknown-entry message with optional suggestions.

        This helper standardizes the user-facing output shown when a command or
        namespace token cannot be resolved. When suggestions are available, it
        renders a "did you mean" style message; otherwise it prints a direct
        not-found error.

        Args:
            key (str): Raw token the user attempted to invoke.
            suggestions (list[str]): Candidate entry names returned by resolution.
            message_context (str): Optional label describing the lookup context, such as
                "TLDR example".
        """
        if message_context:
            message_context = f"'{message_context}' "
        if not suggestions:
            self.console.print(
                f"[{OneColors.DARK_RED}]❌ {message_context}No command or namespace found for '{key}'.[/]"
            )
            return None
        self.console.print(
            f"[{OneColors.LIGHT_YELLOW}]⚠️ {message_context}Unknown command or namespace '{key}'.\nDid you mean: [/]"
            f"{', '.join(suggestions)[:10]}"
        )

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
        """
        entry, suggestions = self.resolve_entry(entry_key)
        if not entry:
            self._print_suggestions_message(
                entry_key, suggestions, message_context="TLDR example"
            )
            return None
        self._tldr_examples.append(
            FalyxTLDRExample(entry_key=entry_key, usage=usage, description=description)
        )

    def add_tldr_examples(self, examples: list[FalyxTLDRInput]) -> None:
        """Register multiple namespace-level TLDR examples.

        Supports either `FalyxTLDRExample` objects or shorthand tuples of
        `(entry_key, usage, description)`.

        Args:
            examples (list[FalyxTLDRInput]): Example definitions to validate and append.

        Raises:
            FalyxError: If an example has an unsupported shape.
        """
        for example in examples:
            if isinstance(example, FalyxTLDRExample):
                entry, suggestions = self.resolve_entry(example.entry_key)
                if not entry:
                    self._print_suggestions_message(
                        example.entry_key, suggestions, message_context="TLDR example"
                    )
                    continue
                self._tldr_examples.append(example)
            elif len(example) == 3:
                entry_key, usage, description = example
                self.add_tldr_example(
                    entry_key=entry_key,
                    usage=usage,
                    description=description,
                )
            else:
                raise FalyxError(
                    f"Invalid TLDR example format: {example}. "
                    "Examples must be either FalyxTLDRExample instances "
                    "or tuples of (entry_key, usage, description).",
                )

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
            FalyxError: If `options` is provided but is not an `OptionsManager`.
        """
        self.options: OptionsManager = options or OptionsManager()
        if not isinstance(self.options, OptionsManager):
            raise FalyxError("Options must be an instance of OptionsManager.")

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
                        f"Identifier '{norm}' is already registered.\n"
                        f"Existing entry: {mapping[norm].key}\n"
                        f"New entry: {entry.key}"
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
        parser = CommandArgumentParser(
            command_key="Y",
            command_description="History",
            command_style=OneColors.DARK_YELLOW,
            aliases=["HISTORY"],
            program=self.program,
            options_manager=self.options,
        )
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
            arg_parser=parser,
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
            invocation_context (InvocationContext | None): Optional routed invocation context used to scope the
                rendered usage path.
        """
        if not isinstance(command, Command):
            self.console.print(
                f"Entry '{command.key}' is not a command.", style=OneColors.DARK_RED
            )
            return None
        if command.render_tldr(invocation_context=invocation_context):
            if self.enable_help_tips:
                self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")
        else:
            self.console.print(
                f"[bold]No TLDR examples available for '{command.description}'.[/bold]"
            )

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
            invocation_context (InvocationContext | None): Optional routed invocation context used to scope the
                rendered usage path.
        """
        if not isinstance(command, Command):
            self.console.print(
                f"Entry '{command.key}' is not a command.", style=OneColors.DARK_RED
            )
            return None
        if tldr:
            await self._render_command_tldr(
                command, invocation_context=invocation_context
            )
        elif command.render_help(invocation_context=invocation_context):
            if self.enable_help_tips:
                self.console.print(f"\n[bold]tip:[/bold] {self.get_tip()}")
        else:
            self.console.print(
                f"[bold]No detailed help available for '{command.description}'.[/bold]"
            )

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

    async def _render_menu_help(self) -> None:
        """Render the interactive menu-style help view for this namespace.

        The menu help view displays user commands plus the special help, history,
        and exit entries using panel-based Rich rendering.
        """
        self.console.print("[bold]help:[/bold]")
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
        if self.help_command:
            usage, description, _ = self.help_command.help_signature
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
        if self.enable_help_tips:
            self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")

    def _get_usage(self, invocation_context: InvocationContext) -> str:
        """Build the default namespace usage fragment for the given context.

        Usage text is aware of whether the current namespace exposes nested
        namespaces and whether rendering is happening in CLI or menu mode.

        Args:
            invocation_context (InvocationContext): Routed invocation context for the current help
                target.

        Returns:
            str: Escaped usage fragment suitable for Rich output.
        """
        has_namespaces = any(not ns.hidden for ns in self.namespaces.values())
        target = "command" if not has_namespaces else "command or namespace"
        if not invocation_context.typed_path and invocation_context.is_cli_mode:
            return escape(f"[-h] [-T] [-v] [-d] [-n] <{target}> [args...]")
        elif not invocation_context.typed_path:
            return escape(f"[-h] [-T] <{target}> [args...]")
        return escape(f"<{target}> [args...]")

    async def _render_namespace_tldr_help(
        self, invocation_context: InvocationContext
    ) -> None:
        """Render namespace-level TLDR examples for the current scope.

        This prints usage, optional namespace description, and all registered TLDR
        examples using the routed invocation path supplied by the context.

        Args:
            invocation_context (InvocationContext): Routed invocation context for the namespace being
                rendered.
        """
        if not self._tldr_examples:
            self.console.print(
                f"[bold]No TLDR examples available for '{self._get_title()}'.[/bold]"
            )
            return None
        usage = self.usage or self._get_usage(invocation_context)
        prefix = invocation_context.markup_path
        self.console.print(
            f"[bold]usage:[/bold] {prefix} [{self.usage_style}]{usage}[/{self.usage_style}]"
        )
        if self.description:
            self.console.print(
                f"\n[{self.description_style}]{self.description}[/{self.description_style}]"
            )
        if self._tldr_examples:
            self.console.print("\n[bold]examples:[/bold]")
            for example in self._tldr_examples:
                entry, suggestions = self.resolve_entry(example.entry_key)
                if not entry:
                    self._print_suggestions_message(
                        example.entry_key, suggestions, message_context="TLDR example"
                    )
                    continue
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
            invocation_context (InvocationContext | None): Optional routed invocation context. When omitted, a
                fresh root context is created.
            tldr (bool): Whether to render namespace TLDR output instead of standard help.
        """
        invocation_context = invocation_context or self.get_current_invocation_context()
        if tldr:
            await self._render_namespace_tldr_help(invocation_context)
        elif invocation_context.mode is FalyxMode.MENU:
            await self._render_menu_help()
        else:
            await self._render_cli_help(invocation_context)

    async def _render_cli_help(self, invocation_context: InvocationContext) -> None:
        """Render the CLI-style help view for this namespace.

        The output includes usage, description, global options, builtin commands,
        user commands, and optional epilog content.

        Args:
            invocation_context (InvocationContext): Routed invocation context used to render the current
                invocation path.
        """
        usage = self.usage or self._get_usage(invocation_context)
        self.console.print(
            f"[bold]usage:[/bold] {invocation_context.markup_path} [{self.usage_style}]{usage}[/{self.usage_style}]"
        )
        if self.description:
            self.console.print(
                f"\n[{self.description_style}]{self.description}[/{self.description_style}]"
            )
        self.console.print("\n[bold]global options:[/bold]")
        self.console.print(f"  {'-h, --help':<22}{'Show this help message and exit.'}")
        self.console.print(f"  {'-T, --tldr':<22}{'Show quick usage examples and exit.'}")
        self.console.print(
            f"  {'-v, --verbose':<22}{'Enable verbose debug logging for the session.'}"
        )
        self.console.print(
            f"  {'--debug-hooks':<22}{'Log detailed information about hook execution for debugging.'}"
        )
        self.console.print(
            f"  {'--never-prompt':<22}{'Disable all confirmation prompts for the entire session.'}"
        )
        self.console.print("\n[bold]builtin commands:[/bold]")
        for command in self.builtins.values():
            if command == self.help_command:
                builtin_alias = Text("help", style=command.style)
            else:
                builtin_alias = Text(command.key, style=command.style)

            line = Text("  ")
            line.append(builtin_alias)
            line.pad_right(24 - len(line.plain))
            line.append(command.help_text)

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
                self._print_suggestions_message(key, suggestions)
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
        parser = CommandArgumentParser(
            command_key="H",
            command_description="Help",
            command_style=OneColors.LIGHT_YELLOW,
            aliases=["HELP", "?"],
            program=self.program,
            options_manager=self.options,
        )
        parser.mark_as_help_command()
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
                ("-Tk [COMMAND]", "Show quick usage examples for a specific command."),
                ("-T", "Show these quick usage examples."),
                ("-t [TAG]", "Show commands with the specified tag."),
            ]
        )
        return Command(
            key="H",
            aliases=["HELP", "?"],
            description="Help",
            help_text="Show this help menu.",
            action=Action("Help", self.render_help),
            style=OneColors.LIGHT_YELLOW,
            arg_parser=parser,
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
            self.console.print(
                f"❌ Entry '{key}' is a namespace. Please specify a command to preview.",
                style=OneColors.DARK_RED,
            )
        elif isinstance(entry, Command):
            self.console.print(f"Preview of command '{entry.key}': {entry.description}")
            await entry.preview()
        else:
            self._print_suggestions_message(key, suggestions)

    def _get_preview_command(self) -> Command:
        """Create the built-in preview command.

        The preview command accepts a command key or alias and delegates to
        `_preview()`.

        Returns:
            Command: Configured preview command instance.
        """
        preview_parser = CommandArgumentParser(
            command_key="preview",
            command_description="Preview",
            command_style=OneColors.GREEN,
            program=self.program,
            options_manager=self.options,
            help_text="Preview the execution of a command without running it.",
        )
        preview_parser.add_argument(
            "key",
            help="The key or alias of the command to preview.",
        )
        preview_parser.add_tldr_examples(
            [
                ("[COMMAND]", "Preview the execution of a specific command."),
            ]
        )
        preview_command = Command(
            key="preview",
            description="Preview",
            action=Action("Preview", self._preview),
            style=OneColors.GREEN,
            simple_help_signature=True,
            options_manager=self.options,
            program=self.program,
            help_text="Preview the execution of a command without running it.",
            arg_parser=preview_parser,
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
            key="version",
            description="Version",
            action=Action("Version", self._render_version),
            style=self.version_style,
            simple_help_signature=True,
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
                "Bottom bar must be a string, callable, None, or BottomBar instance."
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
            InvalidActionError: If any supplied hook is not callable.
        """
        hook_list = hooks if isinstance(hooks, list) else [hooks]
        for hook in hook_list:
            if not callable(hook):
                raise InvalidActionError("Hook must be a callable.")
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
            raise CommandAlreadyExistsError("Duplicate aliases provided.")

        if key in aliases:
            raise CommandAlreadyExistsError("Command key cannot also be an alias.")

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
                f"Command identifiers {sorted(collisions)} already exist."
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
            raise InvalidActionError("Action must be a callable.")
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
    ) -> None:
        """Register a nested `Falyx` instance as a namespace entry.

        The submenu becomes part of routing, completion, and help output in the
        current namespace. When the submenu still uses the default exit command, it
        is converted to a back command automatically.

        Args:
            key (str): Namespace key used to enter the submenu.
            description (str): User-facing namespace description.
            submenu (Falyx): Nested `Falyx` instance to register.
            style (str | None): Optional style override for the namespace entry.
            aliases (list[str] | None): Optional aliases for the namespace.
            help_text (str): Optional help text for namespace listings.

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
            commands (list[Command] | list[dict]): Sequence of `Command` objects or `add_command()` keyword
                dictionaries.

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
                    "Command must be a dictionary or an instance of Command."
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
        table = Table(title=self.title, show_header=False, box=box.SIMPLE)  # type: ignore[arg-type]
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
    ) -> tuple[RouteResult | None, tuple, dict[str, Any], dict[str, Any]]:
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
            tuple[RouteResult | None, tuple, dict[str, Any], dict[str, Any]]:
                Resolved route, positional args, keyword args, and execution args.
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
                        cursor_position=len(raw_arguments), message=str(error)
                    ) from error
                self.console.print(
                    f"Parse error: {error}",
                    style=OneColors.DARK_RED,
                )
                return None, args, kwargs, execution_args
        elif isinstance(raw_arguments, list):
            tokens = raw_arguments
        else:
            if from_validate:
                raise ValidationError(
                    cursor_position=len(raw_arguments),
                    message="TypeError",
                )
            return None, args, kwargs, execution_args

        is_preview = False
        if tokens and tokens[0].startswith("?"):
            is_preview = True
            tokens[0] = tokens[0][1:]

        context = InvocationContext(
            program=self.program,
            program_style=self.program_style,
            typed_path=[],
            mode=mode or self.options.get("mode"),
            is_preview=is_preview,
        )

        route = await self.resolve_route(tokens, invocation_context=context)

        if is_preview:
            route.is_preview = True
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
                    raise ValidationError(
                        cursor_position=len(raw_arguments), message=str(error)
                    ) from error
                else:
                    route.command.render_help(invocation_context=route.context)
                    self.console.print(
                        f"[{OneColors.DARK_RED}]❌ [{route.command.key}]: {error}"
                    )
                    raise error
            except HelpSignal:
                if not from_validate:
                    raise
            return route, args, kwargs, execution_args

        return route, args, kwargs, execution_args

    async def _render_unknown_route(self, route: RouteResult) -> None:
        """Render help plus suggestions for an unresolved route.

        Args:
            route (RouteResult): Unknown route returned by namespace resolution.
        """
        context = route.context
        typed_key = context.typed_path[0].upper()
        await route.namespace.render_namespace_help(context)
        self._print_suggestions_message(typed_key, route.suggestions)
        return None

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
            execution_args (dict[str, Any] | None): Execution-only arguments such as confirmation or retry
                overrides.
            raise_on_error (bool): Whether executor errors should be re-raised.
            wrap_errors (bool): Whether executor errors should be wrapped as `FalyxError`.
            summary_last_result (bool): Whether summary output should only have the last
                result when supported.

        Returns:
            Any | None: Command result for executed leaf commands, otherwise `None`.
        """
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
                self.console.print(
                    f"[{OneColors.DARK_RED}]Error: No command specified for execution mode.[/]"
                )
                if wrap_errors or raise_on_error:
                    raise FalyxError
                return None

            command = route.command

            if route.is_preview:
                logger.info("Preview command '%s' selected.", command.key)
                await command.preview()
                return None

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

        Notes:
            - `HelpSignal` and `CommandArgumentError` are handled internally and do
            not propagate to the caller.
            - This method is the primary programmatic entrypoint for executing a
            command from a raw input string outside the interactive menu loop.
        """
        try:
            route, args, kwargs, execution_args = await self.prepare_route(
                raw_arguments, mode=mode
            )
        except (CommandArgumentError, Exception):
            return None
        except HelpSignal:
            return None

        if route is None:
            return None

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
                # Let the completer suggest entries or namespace-level help flags.
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

        Returns:
            RouteResult: Final routed result for the supplied token path.
        """
        # 1. No more tokens -> this namespace itself was targeted
        if not tokens:
            return RouteResult(
                kind=RouteKind.NAMESPACE_MENU,
                namespace=self,
                context=invocation_context,
            )

        head, *tail = tokens

        # 2. Namespace-level help/tldr belongs to the current namespace
        if head in {"-h", "--help"}:
            return RouteResult(
                kind=RouteKind.NAMESPACE_HELP,
                namespace=self,
                context=invocation_context,
            )

        if head in {"-T", "--tldr"}:
            return RouteResult(
                kind=RouteKind.NAMESPACE_TLDR,
                namespace=self,
                context=invocation_context,
            )

        # 3. Resolve the next entry in this namespace
        entry, suggestions = self.resolve_entry(head)
        if entry is None:
            return RouteResult(
                kind=RouteKind.UNKNOWN,
                namespace=self,
                context=invocation_context,
                suggestions=suggestions,
            )

        route_context = invocation_context.with_path_segment(head, style=entry.style)

        # 4. Namespace entry -> recurse with remaining tokens
        if isinstance(entry, FalyxNamespace):
            return await entry.namespace.resolve_route(
                tail, invocation_context=route_context
            )

        # 5. Leaf command -> stop routing; leave tail untouched for leaf parser
        return RouteResult(
            kind=RouteKind.COMMAND,
            namespace=self,
            context=route_context,
            command=entry,
            leaf_argv=tail,
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
        await self.execute_command(
            raw_arguments,
            raise_on_error=False,
            wrap_errors=False,
            summary_last_result=True,
        )

    def _print_message(self, message: str | Markdown | dict[str, Any]) -> None:
        """Print a startup or exit message using the configured console.

        Args:
            message (str | Markdown | dict[str, Any]): Plain string, `Markdown`,
                or a Rich-print argument dictionary.

        Raises:
            TypeError: If the message is not a supported type.
        """
        if isinstance(message, (str, Markdown)):
            self.console.print(message)
        elif isinstance(message, dict):
            self.console.print(
                *message.get("args", tuple()),
                **message.get("kwargs", {}),
            )
        else:
            raise TypeError(
                "Message must be a string, Markdown, or dictionary with args and kwargs."
            )

    def _get_title(self) -> str:
        """Return the menu title as plain text.

        This normalizes string and `Markdown` title inputs into a single text value
        for logging and display helpers.

        Returns:
            str: Plain-text title for the current namespace.
        """
        if isinstance(self.title, str):
            return self.title
        elif isinstance(self.title, Markdown):
            return self.title.markup
        return self.title

    async def menu(self) -> None:
        """Run the interactive menu loop for this namespace.

        The menu loop renders the current table view, reads commands from the prompt
        session, handles navigation and cancellation signals, and prints optional
        welcome and exit messages.
        """
        logger.info("Starting menu: %s", self._get_title())
        self.options.set("mode", FalyxMode.MENU)
        if self.welcome_message:
            self._print_message(self.welcome_message)
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
            logger.info("Exiting menu: %s", self._get_title())
            if self.exit_message:
                self._print_message(self.exit_message)

    def _apply_parse_result(self, result: RootParseResult) -> None:
        """Apply parsed root/session options to runtime state.

        This updates the active mode, logging verbosity, debug-hook registration,
        and prompt behavior based on the root parse result.

        Args:
            result (RootParseResult): Parsed root CLI result to apply.
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

    async def run(
        self,
        callback: Callable[..., Any] | None = None,
        always_start_menu: bool = False,
    ) -> None:
        """Execute the Falyx application using CLI-driven dispatch.

        This method is the primary entrypoint for Falyx applications.

        - parses root CLI flags using `FalyxParser`
        - optionally invokes a post-parse callback
        - applies session/runtime options
        - renders help immediately when requested
        - prepares and dispatches the routed command
        - exits with CLI-appropriate status codes
        - optionally falls through to interactive menu mode

        Callback Behavior:
        - If provided, `callback` is executed after parsing but before dispatch
        - Supports both sync and async callables
        - Useful for logging setup, environment initialization, etc.

        Args:
            callback (Callable[..., Any] | None):
                Optional function invoked after CLI parsing with the `ParseResult`.
            always_start_menu (bool): Whether to enter menu mode after a successful
                command dispatch when the route itself does not already target help
                or a namespace menu.

        Raises:
            FalyxError:
                If callback is invalid or command execution fails.
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
        parse_result = FalyxParser.parse(sys.argv[1:])

        if callback:
            if not callable(callback):
                raise FalyxError("Callback must be a callable function.")
            async_callback = ensure_async(callback)
            await async_callback(parse_result)

        self._apply_parse_result(parse_result)

        if parse_result.mode == FalyxMode.HELP:
            await self.render_help(namespace_tldr=parse_result.tldr_requested)
            sys.exit(0)

        try:
            route, args, kwargs, execution_args = await self.prepare_route(
                raw_arguments=parse_result.remaining_argv,
            )
        except CommandArgumentError:
            sys.exit(2)
        except HelpSignal:
            sys.exit(0)

        if not route:
            await self.render_help()
            self.console.print(
                f"[{OneColors.DARK_RED}]❌ Error unable to parse: {parse_result.raw_argv}"
            )
            sys.exit(2)

        try:
            await self._dispatch_route(
                route=route,
                args=args,
                kwargs=kwargs,
                execution_args=execution_args,
                raise_on_error=False,
                wrap_errors=True,
            )
        except FalyxError as error:
            self.console.print(f"[{OneColors.DARK_RED}]❌ Error: {error}[/]")
            sys.exit(1)
        except Exception:
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
