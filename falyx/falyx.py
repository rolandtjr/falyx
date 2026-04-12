# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""Falyx CLI framework core module.

This module defines the `Falyx` class, the primary orchestration layer for
building and running structured CLI applications. It integrates command
registration, interactive menu handling, CLI parsing, execution lifecycle
management, and option scoping into a unified runtime.

Core responsibilities:
- Manage command registration, alias resolution, and dispatch
- Coordinate interactive menu and non-interactive CLI execution modes
- Integrate with `FalyxParser` for root-level argument parsing and routing
- Apply execution-scoped overrides via `OptionsManager`
- Drive lifecycle hooks (`before`, `on_success`, `on_error`, `after`, `on_teardown`)
- Provide Rich-based rendering and Prompt Toolkit interaction
- Maintain execution history via `ExecutionRegistry`

Execution Flow:
1. CLI arguments are parsed via `FalyxParser`
2. A `ParseResult` determines the execution mode (menu, command, help, etc.)
3. Execution options are applied through scoped namespaces
4. Commands are resolved and executed via `Command` and `Action` abstractions
5. Lifecycle hooks and context tracking are applied throughout execution

This module serves as the entrypoint for most Falyx-based applications and
coordinates all major subsystems including parsing, execution, rendering,
and state management.
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

    `Falyx` coordinates command registration, input parsing, execution dispatch,
    and lifecycle management across both interactive (menu) and non-interactive
    (CLI) modes.

    It acts as the central integration point between:
    - Command definitions (`Command`)
    - Execution units (`Action`, `ChainedAction`, `ActionGroup`)
    - CLI parsing (`FalyxParser`, `CommandArgumentParser`)
    - Runtime configuration (`OptionsManager`)
    - Lifecycle hooks (`HookManager`)
    - UI layers (Rich + Prompt Toolkit)

    Key Responsibilities:
    - Maintain a registry of commands, aliases, and builtins
    - Resolve user input to commands via exact match, prefix match, or fuzzy match
    - Dispatch execution with full lifecycle hook support
    - Apply execution-scoped option overrides (e.g. confirm, retries)
    - Support both CLI-driven execution and interactive menu loops
    - Provide structured help, preview, and history functionality

    Execution Modes:
    - MENU: Interactive prompt loop using Prompt Toolkit
    - COMMAND: Direct CLI command execution
    - HELP: Render help output
    - ERROR: Render error and exit

    State Management:
    - Uses `OptionsManager` with namespaced overrides (e.g. "execution")
    - Tracks last executed command and execution context
    - Integrates with `ExecutionRegistry` for history and summaries

    Design Notes:
    - Commands are first-class and may encapsulate complex workflows
    - Execution options are parsed separately from command arguments
    - All execution passes through a unified hook lifecycle
    - CLI and menu modes share the same execution semantics

    Args:
        title (str | Markdown): Title displayed for the menu.
        program (str | None): CLI program name used in help output.
        usage (str | None): Optional usage string override.
        description (str | None): Program description for CLI help.
        epilog (str | None): Additional help text.
        version (str): Program version string.
        program_style (str): Rich style for program name in help.
        usage_style (str): Rich style for usage string in help.
        description_style (str): Rich style for description in help.
        epilog_style (str): Rich style for epilog in help.
        version_style (str): Rich style for version in help.
        prompt (str | StyleAndTextTuples): Input prompt.
        columns (int): Number of columns in menu display.
        bottom_bar (BottomBar | str | Callable | None): Bottom bar renderer.
        welcome_message (str | Markdown | dict): Message shown on startup.
        exit_message (str | Markdown | dict): Message shown on exit.
        key_bindings (KeyBindings | None): Custom Prompt Toolkit key bindings.
        include_history_command (bool): Whether to include history command.
        never_prompt (bool): Default prompt suppression setting.
        force_confirm (bool): Default confirmation behavior.
        options (OptionsManager | None): Initial options manager.
        render_menu (Callable | None): Custom menu renderer.
        custom_table (Callable | Table | None): Custom table builder.
        hide_menu_table (bool): Whether to hide menu table.
        show_placeholder_menu (bool): Show placeholder suggestions.
        prompt_history_base_dir (Path): Directory for prompt history.
        enable_prompt_history (bool): Enable persistent history.
        enable_help_tips (bool): Show random tips in help output.

    Raises:
        FalyxError: If invalid configuration or command registration occurs.
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
        """Initializes the Falyx object."""
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
        self._register_default_builtins()
        self._register_options()
        self._executor = CommandExecutor(
            options=self.options,
            hooks=self.hooks,
            console=self.console,
        )

    def get_current_invocation_context(self) -> InvocationContext:
        """Returns the current invocation context."""
        return InvocationContext(
            program=self.program,
            program_style=self.program_style,
            typed_path=[],
            mode=self.options.get("mode"),
        )

    @property
    def is_cli_mode(self) -> bool:
        """Checks if the current mode is a CLI mode."""
        return self.options.get("mode") != FalyxMode.MENU

    def _validate_options(
        self,
        options: OptionsManager | None = None,
    ) -> None:
        """Checks if the options are set correctly."""
        self.options: OptionsManager = options or OptionsManager()
        if not isinstance(self.options, OptionsManager):
            raise FalyxError("Options must be an instance of OptionsManager.")

    def _register_options(self) -> None:
        """Registers default options if they are not already set."""
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

        if not self.options.get("invocation_path"):
            self.options.set("invocation_path", self.program)

    @property
    def _entry_map(self) -> dict[str, Command | FalyxNamespace]:
        """Builds a mapping of all valid input names to Command objects.

        If a collision occurs, logs a warning and keeps the first
        registered command.
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

        for special in [self.exit_command, self.history_command]:
            if special:
                register(special.key, special)
                for alias in special.aliases:
                    register(alias, special)
                register(special.description, special)

        for command in self.builtins.values():
            register(command.key, command)
            for alias in command.aliases:
                register(alias, command)
            register(command.description, command)

        for command in self.commands.values():
            register(command.key, command)
            for alias in command.aliases:
                register(alias, command)
            register(command.description, command)

        for namespace in self.namespaces.values():
            register(namespace.key, namespace)
            for alias in namespace.aliases:
                register(alias, namespace)
        return mapping

    def get_title(self) -> str:
        """Returns the string title of the menu."""
        if isinstance(self.title, str):
            return self.title
        elif isinstance(self.title, Markdown):
            return self.title.markup
        return self.title

    def _get_exit_command(self) -> Command:
        """Returns the back command for the menu."""
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
        """Returns the history command for the menu."""
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
        """Returns a random tip for the user about using Falyx."""
        program = f"{self.program} " if self.is_cli_mode else ""
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
        if self.is_cli_mode:
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
        context: InvocationContext | None = None,
    ) -> None:
        """Renders the TLDR examples for a command, if available."""
        if not isinstance(command, Command):
            self.console.print(
                f"Entry '{command.key}' is not a command.", style=OneColors.DARK_RED
            )
            return None
        if command.render_tldr(invocation_context=context):
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
        context: InvocationContext | None = None,
    ) -> None:
        """Renders the detailed help for a command, if available."""
        if not isinstance(command, Command):
            self.console.print(
                f"Entry '{command.key}' is not a command.", style=OneColors.DARK_RED
            )
            return None
        if tldr:
            await self._render_command_tldr(command, context=context)
        elif command.render_help(invocation_context=context):
            if self.enable_help_tips:
                self.console.print(f"\n[bold]tip:[/bold] {self.get_tip()}")
        else:
            self.console.print(
                f"[bold]No detailed help available for '{command.description}'.[/bold]"
            )

    async def _render_tag_help(self, tag: str) -> None:
        """Renders a list of commands matching a specific tag."""
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
        """Renders the main menu help menu with all commands and menu builtins."""
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

    async def _render_unknown_route(self, route: RouteResult) -> None:
        context = route.context
        typed_key = context.typed_path[0].upper()
        await route.namespace.render_namespace_help(context)
        self.console.print(
            f"[{OneColors.DARK_RED}]❌ Unknown Command or FalyxNamespace [{typed_key}]"
        )
        return None

    async def _render_namespace_tldr_help(self, context: InvocationContext) -> None:
        # TODO: Create namespace tldr
        console.print(context.markup_path)

    async def render_namespace_help(
        self, context: InvocationContext, tldr: bool = False
    ) -> None:
        if tldr:
            await self._render_namespace_tldr_help(context)
        elif context.mode is FalyxMode.MENU:
            await self._render_menu_help()
        else:
            await self._render_cli_help(context)

    async def _render_cli_help(self, context: InvocationContext) -> None:
        """Renders the CLI help menu with all available commands and options."""
        usage = self.usage or "[GLOBAL OPTIONS] [COMMAND] [OPTIONS]"
        self.console.print(
            f"[bold]usage:[/bold] {context.markup_path} [{self.usage_style}]{usage}[/{self.usage_style}]"
        )
        if self.description:
            self.console.print(
                f"\n[{self.description_style}]{self.description}[/{self.description_style}]"
            )
        self.console.print("\n[bold]global options:[/bold]")
        self.console.print(f"  {'-h, --help':<22}{'Show this help message and exit.'}")
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

    def _help_target_base_context(self, context: InvocationContext) -> InvocationContext:
        if not context.typed_path:
            return context

        last_token = context.typed_path[-1]
        entry, _ = self.resolve_entry(last_token)

        if entry is self.help_command:
            return context.without_last_path_segment()

        return context

    async def render_help(
        self,
        tag: str = "",
        key: str | None = None,
        tldr: bool = False,
        invocation_context: InvocationContext | None = None,
    ) -> None:
        """Renders the help menu with command details, usage examples, and tips."""
        context = invocation_context or self.get_current_invocation_context()
        if key:
            entry, suggestions = self.resolve_entry(key)
            if suggestions:
                self.console.print(
                    f"[{OneColors.LIGHT_YELLOW}]⚠️  Unknown entry '{key}'. Did you mean:[/]"
                    f"{', '.join(suggestions)[:10]}"
                )
                return None

            base_context = self._help_target_base_context(context)

            if isinstance(entry, Command):
                await self._render_command_help(
                    command=entry,
                    tldr=tldr,
                    context=base_context.with_path_segment(key, style=entry.style),
                )
            elif isinstance(entry, FalyxNamespace):
                await entry.namespace.render_namespace_help(
                    context=base_context.with_path_segment(key, style=entry.style),
                    tldr=tldr,
                )
            else:
                # TODO: Should print something helpful here
                self.console.print(
                    f"[{OneColors.DARK_RED}]❌ No entry found for '{key}'.[/]"
                )
        elif tldr:
            await self._render_command_help(
                self.help_command,
                tldr,
                context=context,
            )
        elif tag:
            await self._render_tag_help(tag)
        elif self.options.get("mode") == FalyxMode.MENU:
            await self._render_menu_help()
        else:
            await self._render_cli_help(context)

    def _get_help_command(self) -> Command:
        """Returns the help command for the menu."""
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
        """Previews the execution of a command without actually running it."""
        entry, suggestions = self.resolve_entry(key)
        if suggestions:
            self.console.print(
                f"[{OneColors.LIGHT_YELLOW}]⚠️  Unknown entry '{key}'. Did you mean:[/]"
                f"{', '.join(suggestions)[:10]}"
            )
            return None
        if isinstance(entry, FalyxNamespace):
            self.console.print(
                f"❌ Entry '{key}' is a namespace. Please specify a command to preview.",
                style=OneColors.DARK_RED,
            )
            return None
        if not isinstance(entry, Command):
            self.console.print(f"[{OneColors.DARK_RED}]❌ No entry found for '{key}'.[/]")
            return None
        self.console.print(f"Preview of command '{entry.key}': {entry.description}")
        await entry.preview()

    def _get_preview_command(self) -> Command:
        """Returns the preview command for Falyx."""
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
        """Renders the program version."""
        self.console.print(f"[{self.version_style}]{self.program} v{self.version}[/]")

    def _get_version_command(self) -> Command:
        """Returns the version command for Falyx."""
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
        """Adds a built-in command to Falyx."""
        self._validate_command_aliases(command.key, command.aliases)
        self.builtins[command.key.upper()] = command
        _ = self._entry_map

    def _register_default_builtins(self) -> None:
        """Registers the default built-in commands for Falyx."""
        self._add_builtin(self.help_command)
        self._add_builtin(self._get_preview_command())
        self._add_builtin(self._get_version_command())

    def _get_completer(self) -> FalyxCompleter:
        """Completer to provide auto-completion for the menu commands."""
        return FalyxCompleter(self)

    def _get_validator_error_message(self) -> str:
        """Validator to check if the input is a valid command."""
        visible = self.iter_visible_entries(
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
        """Forces the prompt session to be recreated on the next access."""
        if hasattr(self, "prompt_session"):
            del self.prompt_session
        self._prompt_session = None

    @property
    def bottom_bar(self) -> BottomBar | str | Callable[[], Any] | None:
        """Returns the bottom bar for the menu."""
        return self._bottom_bar

    @bottom_bar.setter
    def bottom_bar(self, bottom_bar: BottomBar | str | Callable[[], Any] | None) -> None:
        """Sets the bottom bar for the menu."""
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
        """Returns the bottom bar for the menu."""
        if isinstance(self.bottom_bar, BottomBar) and self.bottom_bar.has_items:
            return self.bottom_bar.render
        elif callable(self.bottom_bar):
            return self.bottom_bar
        elif isinstance(self.bottom_bar, str):
            return self.bottom_bar
        return None

    @cached_property
    def prompt_session(self) -> PromptSession:
        """Returns the prompt session for the menu."""
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
        """Registers hooks for all commands in the menu and actions recursively."""
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
        """Registers debug hooks for all commands in the menu and actions recursively."""
        self.register_all_hooks(HookType.BEFORE, log_before)
        self.register_all_hooks(HookType.ON_SUCCESS, log_success)
        self.register_all_hooks(HookType.ON_ERROR, log_error)
        self.register_all_hooks(HookType.AFTER, log_after)
        self.register_all_hooks(HookType.ON_TEARDOWN, log_after)

    def _validate_command_aliases(self, key: str, aliases: list[str] | None) -> None:
        """Validates the command aliases to ensure they are unique."""
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
        """Updates the back command of the menu."""
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
        """Adds a submenu to the menu."""
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
        """Adds a list of Command instances or config dicts."""
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
        """Adds a command to the menu from an existing Command object."""
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
        """Adds an command to the menu, preventing duplicates."""
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

    def get_bottom_row(self) -> list[str]:
        """Returns the bottom row of the table for displaying additional commands."""
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

    def iter_visible_entries(
        self,
        *,
        include_builtins: bool = False,
        include_help: bool = False,
        include_history: bool = False,
        include_exit: bool = False,
    ) -> list[Command | FalyxNamespace]:
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
        """Build the standard table layout.

        Developers can subclass or call this in custom tables.
        """
        table = Table(title=self.title, show_header=False, box=box.SIMPLE)  # type: ignore[arg-type]
        visible = self.iter_visible_entries()
        for chunk in chunks(visible, self.columns):
            row = []
            for entry in chunk:
                escaped_key = escape(f"[{entry.key}]")
                row.append(f"{escaped_key} [{entry.style}]{entry.description}")
            table.add_row(*row)
        bottom_row = self.get_bottom_row()
        for row in chunks(bottom_row, self.columns):
            table.add_row(*row)
        return table

    def build_placeholder_menu(self) -> StyleAndTextTuples:
        """Builds a menu placeholder for show_placeholder_menu."""
        visible_commands = [item for item in self.commands.items() if not item[1].hidden]
        if not visible_commands:
            return [("", "")]

        placeholder: list[str] = []
        for key, command in visible_commands:
            placeholder.append(f"[{key}] [{command.style}]{command.description}[/]")
        for command_str in self.get_bottom_row():
            placeholder.append(command_str)

        return rich_text_to_prompt_text(" ".join(placeholder))

    @property
    def table(self) -> Table:
        """Creates or returns a custom table to display the menu commands."""
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

    def parse_preview_command(self, input_str: str) -> tuple[bool, str]:
        """Checks if the input is a preview command and returns the command key if so."""
        if input_str.startswith("?"):
            return True, input_str[1:].strip()
        return False, input_str.strip()

    def resolve_entry(
        self,
        token: str,
    ) -> tuple[Command | FalyxNamespace | None, list[str]]:
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

        route = await self.resolve_route(tokens, context=context)

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
            - Raises `QuitSignal` if the resolved command is the configured exit
            command.
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

    async def resolve_route(
        self,
        tokens: list[str],
        *,
        context: InvocationContext,
    ) -> RouteResult:
        # 1. No more tokens -> this namespace itself was targeted
        if not tokens:
            return RouteResult(
                kind=RouteKind.NAMESPACE_MENU,
                namespace=self,
                context=context,
            )

        head, *tail = tokens

        # 2. Namespace-level help/tldr belongs to the current namespace
        if head in {"-h", "--help"}:
            return RouteResult(
                kind=RouteKind.NAMESPACE_HELP,
                namespace=self,
                context=context,
            )

        if head in {"-T", "--tldr"}:
            return RouteResult(
                kind=RouteKind.NAMESPACE_TLDR,
                namespace=self,
                context=context,
            )

        # 3. Resolve the next entry in this namespace
        entry, suggestions = self.resolve_entry(head)
        if entry is None:
            return RouteResult(
                kind=RouteKind.UNKNOWN,
                namespace=self,
                context=context,
                suggestions=suggestions,
            )

        route_context = context.with_path_segment(head, style=entry.style)

        # 4. Namespace entry -> recurse with remaining tokens
        if isinstance(entry, FalyxNamespace):
            return await entry.namespace.resolve_route(tail, context=route_context)

        # 5. Leaf command -> stop routing; leave tail untouched for leaf parser
        return RouteResult(
            kind=RouteKind.COMMAND,
            namespace=self,
            context=route_context,
            command=entry,
            leaf_argv=tail,
        )

    async def process_command(self) -> None:
        """Processes the action of the selected command."""
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

    def print_message(self, message: str | Markdown | dict[str, Any]) -> None:
        """Prints a message to the console."""
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

    async def menu(self) -> None:
        """Runs the menu and handles user input."""
        logger.info("Starting menu: %s", self.get_title())
        self.options.set("mode", FalyxMode.MENU)
        if self.welcome_message:
            self.print_message(self.welcome_message)
        try:
            while True:
                if not self.options.get("hide_menu_table", self._hide_menu_table):
                    if callable(self.render_menu):
                        self.render_menu(self)
                    else:
                        self.console.print(self.table, justify="center")
                try:
                    await self.process_command()
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
            logger.info("Exiting menu: %s", self.get_title())
            if self.exit_message:
                self.print_message(self.exit_message)

    def _apply_parse_result(self, result: RootParseResult) -> None:
        """Applies the parsed CLI arguments to the menu options."""
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

        This method is the primary entrypoint for Falyx applications. It parses
        CLI arguments, configures runtime state, and dispatches execution based
        on the resolved mode.

        Callback Behavior:
        - If provided, `callback` is executed after parsing but before dispatch
        - Supports both sync and async callables
        - Useful for logging setup, environment initialization, etc.

        Args:
            callback (Callable[..., Any] | None):
                Optional function invoked after CLI parsing with the `ParseResult`.
            always_start_menu (bool):
                If True, launches the interactive menu after command execution
                instead of exiting.

        Raises:
            FalyxError:
                If callback is invalid or command execution fails.
            SystemExit:
                Terminates the process with an appropriate exit code based on mode.

        Notes:
            - Most CLI execution paths terminate via `sys.exit()`
            - Interactive mode continues via `menu()`
            - Execution options are applied in a scoped "execution" namespace
            - Preview mode (`?command`) bypasses execution and renders a preview

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
            await self.render_help()
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
