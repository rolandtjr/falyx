# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Main class for constructing and running Falyx CLI menus.

Falyx provides a structured, customizable interactive menu system
for running commands, actions, and workflows. It supports:

- Hook lifecycle management (before/on_success/on_error/after/on_teardown)
- Dynamic command addition and alias resolution
- Rich-based menu display with multi-column layouts
- Interactive input validation and auto-completion
- History tracking and help menu generation
- Confirmation prompts and spinners
- Run key for automated script execution
- CLI argument parsing with argparse integration
- Retry policy configuration for actions

Falyx enables building flexible, robust, and user-friendly
terminal applications with minimal boilerplate.
"""
from __future__ import annotations

import asyncio
import logging
import shlex
import sys
from argparse import ArgumentParser, Namespace, _SubParsersAction
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
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table

from falyx.action.action import Action
from falyx.action.base_action import BaseAction
from falyx.bottom_bar import BottomBar
from falyx.command import Command
from falyx.completer import FalyxCompleter
from falyx.console import console
from falyx.context import ExecutionContext
from falyx.debug import log_after, log_before, log_error, log_success
from falyx.exceptions import (
    CommandAlreadyExistsError,
    CommandArgumentError,
    FalyxError,
    InvalidActionError,
    NotAFalyxError,
)
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.hooks import spinner_before_hook, spinner_teardown_hook
from falyx.logger import logger
from falyx.mode import FalyxMode
from falyx.options_manager import OptionsManager
from falyx.parser import CommandArgumentParser, FalyxParsers, get_arg_parsers
from falyx.prompt_utils import rich_text_to_prompt_text
from falyx.protocols import ArgParserProtocol
from falyx.retry import RetryPolicy
from falyx.signals import BackSignal, CancelSignal, HelpSignal, QuitSignal
from falyx.themes import OneColors
from falyx.utils import CaseInsensitiveDict, _noop, chunks, ensure_async
from falyx.validators import CommandValidator
from falyx.version import __version__


class Falyx:
    """
    Main menu controller for Falyx CLI applications.

    Falyx orchestrates the full lifecycle of an interactive menu system,
    handling user input, command execution, error recovery, and structured
    CLI workflows.

    Key Features:
    - Interactive menu with Rich rendering and Prompt Toolkit input handling
    - Dynamic command management with alias and abbreviation matching
    - Full lifecycle hooks (before, success, error, after, teardown) at both menu and
      command levels
    - Built-in retry support, spinner visuals, and confirmation prompts
    - Submenu nesting and action chaining
    - History tracking, help generation, and run key execution modes
    - Seamless CLI argument parsing and integration via argparse
    - Declarative option management with OptionsManager
    - Command level argument parsing and validation
    - Extensible with user-defined hooks, bottom bars, and custom layouts

    Args:
        title (str | Markdown): Title displayed for the menu.
        prompt (AnyFormattedText): Prompt displayed when requesting user input.
        columns (int): Number of columns to use when rendering menu commands.
        bottom_bar (BottomBar | str | Callable | None): Bottom toolbar content or logic.
        welcome_message (str | Markdown | dict): Welcome message shown at startup.
        exit_message (str | Markdown | dict): Exit message shown on shutdown.
        key_bindings (KeyBindings | None): Custom Prompt Toolkit key bindings.
        include_history_command (bool): Whether to add a built-in history viewer command.
        include_help_command (bool): Whether to add a built-in help viewer command.
        never_prompt (bool): Seed default for `OptionsManager["never_prompt"]`
        force_confirm (bool): Seed default for `OptionsManager["force_confirm"]`
        cli_args (Namespace | None): Parsed CLI arguments, usually from argparse.
        options (OptionsManager | None): Declarative option mappings for global state.
        custom_table (Callable[[Falyx], Table] | Table | None): Custom menu table
                                                                generator.

    Methods:
        run(): Main entry point for CLI argument-based workflows. Suggested for
               most use cases.
        menu(): Run the interactive menu loop.
        run_key(command_key, return_context): Run a command directly without the menu.
        add_command(): Add a single command to the menu.
        add_commands(): Add multiple commands at once.
        register_all_hooks(): Register hooks across all commands and submenus.
        debug_hooks(): Log hook registration for debugging.
        build_default_table(): Construct the standard Rich table layout.
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
        version_style: str = OneColors.BLUE_b,
        prompt: str | StyleAndTextTuples = "> ",
        columns: int = 3,
        bottom_bar: BottomBar | str | Callable[[], Any] | None = None,
        welcome_message: str | Markdown | dict[str, Any] = "",
        exit_message: str | Markdown | dict[str, Any] = "",
        key_bindings: KeyBindings | None = None,
        include_history_command: bool = True,
        include_help_command: bool = True,
        never_prompt: bool = False,
        force_confirm: bool = False,
        cli_args: Namespace | None = None,
        options: OptionsManager | None = None,
        render_menu: Callable[[Falyx], None] | None = None,
        custom_table: Callable[[Falyx], Table] | Table | None = None,
        hide_menu_table: bool = False,
        show_placeholder_menu: bool = False,
        prompt_history_base_dir: Path = Path.home(),
        enable_prompt_history: bool = False,
    ) -> None:
        """Initializes the Falyx object."""
        self.title: str | Markdown = title
        self.program: str = program or ""
        self.usage: str | None = usage
        self.description: str | None = description
        self.epilog: str | None = epilog
        self.version: str = version
        self.version_style: str = version_style
        self.prompt: str | StyleAndTextTuples = rich_text_to_prompt_text(prompt)
        self.columns: int = columns
        self.commands: dict[str, Command] = CaseInsensitiveDict()
        self.console: Console = console
        self.welcome_message: str | Markdown | dict[str, Any] = welcome_message
        self.exit_message: str | Markdown | dict[str, Any] = exit_message
        self.hooks: HookManager = HookManager()
        self.last_run_command: Command | None = None
        self.key_bindings: KeyBindings = key_bindings or KeyBindings()
        self.bottom_bar: BottomBar | str | Callable[[], None] = bottom_bar
        self._never_prompt: bool = never_prompt
        self._force_confirm: bool = force_confirm
        self.cli_args: Namespace | None = cli_args
        self.render_menu: Callable[[Falyx], None] | None = render_menu
        self.custom_table: Callable[[Falyx], Table] | Table | None = custom_table
        self._hide_menu_table: bool = hide_menu_table
        self.show_placeholder_menu: bool = show_placeholder_menu
        self.validate_options(cli_args, options)
        self._prompt_session: PromptSession | None = None
        self.options.set("mode", FalyxMode.MENU)
        self.exit_command: Command = self._get_exit_command()
        self.history_command: Command | None = (
            self._get_history_command() if include_history_command else None
        )
        self.help_command: Command | None = (
            self._get_help_command() if include_help_command else None
        )
        if enable_prompt_history:
            program = (self.program or "falyx").split(".")[0].replace(" ", "_")
            self.history_path: Path = (
                Path(prompt_history_base_dir) / f".{program}_history"
            )
            self.history: FileHistory | None = FileHistory(self.history_path)
        else:
            self.history = None

    @property
    def is_cli_mode(self) -> bool:
        return self.options.get("mode") in {
            FalyxMode.RUN,
            FalyxMode.PREVIEW,
            FalyxMode.RUN_ALL,
            FalyxMode.HELP,
        }

    def validate_options(
        self,
        cli_args: Namespace | None,
        options: OptionsManager | None = None,
    ) -> None:
        """Checks if the options are set correctly."""
        self.options: OptionsManager = options or OptionsManager()
        if not cli_args and not options:
            return None

        if options and not cli_args:
            raise FalyxError("Options are set, but CLI arguments are not.")

        assert isinstance(
            cli_args, Namespace
        ), "CLI arguments must be a Namespace object."

        if not isinstance(self.options, OptionsManager):
            raise FalyxError("Options must be an instance of OptionsManager.")

        if not isinstance(self.cli_args, Namespace):
            raise FalyxError("CLI arguments must be a Namespace object.")

    @property
    def _name_map(self) -> dict[str, Command]:
        """
        Builds a mapping of all valid input names (keys, aliases, normalized names) to
        Command objects. If a collision occurs, logs a warning and keeps the first
        registered command.
        """
        mapping: dict[str, Command] = {}

        def register(name: str, cmd: Command):
            norm = name.upper().strip()
            if norm in mapping:
                existing = mapping[norm]
                if existing is not cmd:
                    logger.warning(
                        "[alias conflict] '%s' already assigned to '%s'. "
                        "Skipping for '%s'.",
                        name,
                        existing.description,
                        cmd.description,
                    )
            else:
                mapping[norm] = cmd

        for special in [self.exit_command, self.history_command, self.help_command]:
            if special:
                register(special.key, special)
                for alias in special.aliases:
                    register(alias, special)
                register(special.description, special)

        for cmd in self.commands.values():
            register(cmd.key, cmd)
            for alias in cmd.aliases:
                register(alias, cmd)
            register(cmd.description, cmd)
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
        return Command(
            key="X",
            description="Exit",
            action=Action("Exit", action=_noop),
            aliases=["EXIT", "QUIT"],
            style=OneColors.DARK_RED,
            simple_help_signature=True,
            ignore_in_history=True,
            options_manager=self.options,
            program=self.program,
            help_text="Exit the program.",
        )

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
        program = f"{self.program} run " if self.is_cli_mode else ""
        tips = [
            f"Use '{program}?[COMMAND]' to preview a command.",
            "Every command supports aliases—try abbreviating the name!",
            f"Use '{program}H' to reopen this help menu anytime.",
            f"'{program}[COMMAND] --help' prints a detailed help message.",
            "[bold]CLI[/] and [bold]Menu[/] mode—commands run the same way in both.",
            f"'{self.program} --never-prompt' to disable all prompts for the [bold italic]entire menu session[/].",
            f"Use '{self.program} --verbose' to enable debug logging for a menu session.",
            f"'{self.program} --debug-hooks' will trace every before/after hook in action.",
            f"Run commands directly from the CLI: '{self.program} run [COMMAND] [OPTIONS]'.",
            "All [COMMAND] keys and aliases are case-insensitive.",
        ]
        if self.is_cli_mode:
            tips.extend(
                [
                    f"Use '{self.program} help' to list all commands at any time.",
                    f"Use '{self.program} --never-prompt run [COMMAND] [OPTIONS]' to disable all prompts for [bold italic]just this command[/].",
                    f"Use '{self.program} run --skip-confirm [COMMAND] [OPTIONS]' to skip confirmations.",
                    f"Use '{self.program} run --summary [COMMAND] [OPTIONS]' to print a post-run summary.",
                    f"Use '{self.program} --verbose run [COMMAND] [OPTIONS]' to enable debug logging for any run.",
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

    async def _render_help(
        self, tag: str = "", key: str | None = None, tldr: bool = False
    ) -> None:
        if tldr and not key:
            if self.help_command and self.help_command.arg_parser:
                self.help_command.arg_parser.render_tldr()
                self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")
                return None
        if key:
            _, command, args, kwargs = await self.get_command(key)
            if command and tldr and command.arg_parser:
                command.arg_parser.render_tldr()
                self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")
                return None
            elif command and tldr and not command.arg_parser:
                self.console.print(
                    f"[bold]No TLDR examples available for '{command.description}'.[/bold]"
                )
            elif command and command.arg_parser:
                command.arg_parser.render_help()
                self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")
                return None
            elif command and not command.arg_parser:
                self.console.print(
                    f"[bold]No detailed help available for '{command.description}'.[/bold]"
                )
            else:
                self.console.print(f"[bold]No command found for '{key}'.[/bold]")
        if tag:
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
            self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")
            return None

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
        if not self.is_cli_mode:
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
        self.console.print(f"[bold]tip:[/bold] {self.get_tip()}")

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
                ("--tldr", "Show these quick usage examples."),
                ("--tag [TAG]", "Show commands with the specified tag."),
            ]
        )
        return Command(
            key="H",
            aliases=["HELP", "?"],
            description="Help",
            help_text="Show this help menu.",
            action=Action("Help", self._render_help),
            style=OneColors.LIGHT_YELLOW,
            arg_parser=parser,
            ignore_in_history=True,
            options_manager=self.options,
            program=self.program,
        )

    def _get_completer(self) -> FalyxCompleter:
        """Completer to provide auto-completion for the menu commands."""
        return FalyxCompleter(self)

    def _get_validator_error_message(self) -> str:
        """Validator to check if the input is a valid command."""
        keys = {self.exit_command.key.upper()}
        keys.update({alias.upper() for alias in self.exit_command.aliases})
        if self.history_command:
            keys.add(self.history_command.key.upper())
            keys.update({alias.upper() for alias in self.history_command.aliases})
        if self.help_command:
            keys.add(self.help_command.key.upper())
            keys.update({alias.upper() for alias in self.help_command.aliases})

        for cmd in self.commands.values():
            keys.add(cmd.key.upper())
            keys.update({alias.upper() for alias in cmd.aliases})

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

    def add_help_command(self):
        """Adds a help command to the menu if it doesn't already exist."""
        if not self.help_command:
            self.help_command = self._get_help_command()

    def add_history_command(self):
        """Adds a history command to the menu if it doesn't already exist."""
        if not self.history_command:
            self.history_command = self._get_history_command()

    @property
    def bottom_bar(self) -> BottomBar | str | Callable[[], Any] | None:
        """Returns the bottom bar for the menu."""
        return self._bottom_bar

    @bottom_bar.setter
    def bottom_bar(self, bottom_bar: BottomBar | str | Callable[[], Any] | None) -> None:
        """Sets the bottom bar for the menu."""
        if bottom_bar is None:
            self._bottom_bar: BottomBar | str | Callable[[], Any] = BottomBar(
                self.columns, self.key_bindings
            )
        elif isinstance(bottom_bar, BottomBar):
            bottom_bar.key_bindings = self.key_bindings
            self._bottom_bar = bottom_bar
        elif isinstance(bottom_bar, str) or callable(bottom_bar):
            self._bottom_bar = bottom_bar
        else:
            raise FalyxError(
                "Bottom bar must be a string, callable, or BottomBar instance."
            )
        self._invalidate_prompt_session_cache()

    def _get_bottom_bar_render(self) -> Callable[[], Any] | str | None:
        """Returns the bottom bar for the menu."""
        if isinstance(self.bottom_bar, BottomBar) and self.bottom_bar._named_items:
            return self.bottom_bar.render
        elif callable(self.bottom_bar):
            return self.bottom_bar
        elif isinstance(self.bottom_bar, str):
            return self.bottom_bar
        elif self.bottom_bar is None:
            return None
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

    def debug_hooks(self) -> None:
        """Logs the names of all hooks registered for the menu and its commands."""
        logger.debug("Menu-level hooks:\n%s", str(self.hooks))

        for key, command in self.commands.items():
            logger.debug("[Command '%s'] hooks:\n%s", key, str(command.hooks))

    def _validate_command_key(self, key: str) -> None:
        """Validates the command key to ensure it is unique."""
        key = key.upper()
        collisions = []

        if key in self.commands:
            collisions.append("command")
        if key == self.exit_command.key.upper():
            collisions.append("back command")
        if self.history_command and key == self.history_command.key.upper():
            collisions.append("history command")
        if self.help_command and key == self.help_command.key.upper():
            collisions.append("help command")

        if collisions:
            raise CommandAlreadyExistsError(
                f"Command key '{key}' conflicts with existing {', '.join(collisions)}."
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
        self._validate_command_key(key)
        action = action or Action(description, action=_noop)
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

    def add_submenu(
        self, key: str, description: str, submenu: Falyx, *, style: str = OneColors.CYAN
    ) -> None:
        """Adds a submenu to the menu."""
        if not isinstance(submenu, Falyx):
            raise NotAFalyxError("submenu must be an instance of Falyx.")
        self._validate_command_key(key)
        self.add_command(
            key, description, submenu.menu, style=style, simple_help_signature=True
        )
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
        self._validate_command_key(command.key)
        self.commands[command.key] = command

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
        custom_parser: ArgParserProtocol | None = None,
        custom_help: Callable[[], str | None] | None = None,
        auto_args: bool = True,
        arg_metadata: dict[str, str | dict[str, Any]] | None = None,
        simple_help_signature: bool = False,
        ignore_in_history: bool = False,
    ) -> Command:
        """Adds an command to the menu, preventing duplicates."""
        self._validate_command_key(key)

        if arg_parser:
            if not isinstance(arg_parser, CommandArgumentParser):
                raise NotAFalyxError(
                    "arg_parser must be an instance of CommandArgumentParser."
                )
            arg_parser = arg_parser

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
            retry=retry,
            retry_all=retry_all,
            retry_policy=retry_policy or RetryPolicy(),
            options_manager=self.options,
            arg_parser=arg_parser,
            arguments=arguments or [],
            argument_config=argument_config,
            custom_parser=custom_parser,
            custom_help=custom_help,
            auto_args=auto_args,
            arg_metadata=arg_metadata or {},
            simple_help_signature=simple_help_signature,
            ignore_in_history=ignore_in_history,
            program=self.program,
        )

        if hooks:
            if not isinstance(hooks, HookManager):
                raise NotAFalyxError("hooks must be an instance of HookManager.")
            command.hooks = hooks

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

        self.commands[key] = command
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

    def build_default_table(self) -> Table:
        """
        Build the standard table layout. Developers can subclass or call this
        in custom tables.
        """
        table = Table(title=self.title, show_header=False, box=box.SIMPLE)  # type: ignore[arg-type]
        visible_commands = [item for item in self.commands.items() if not item[1].hidden]
        for chunk in chunks(visible_commands, self.columns):
            row = []
            for key, command in chunk:
                row.append(f"[{key}] [{command.style}]{command.description}")
            table.add_row(*row)
        bottom_row = self.get_bottom_row()
        for row in chunks(bottom_row, self.columns):
            table.add_row(*row)
        return table

    def build_placeholder_menu(self) -> StyleAndTextTuples:
        """
        Builds a menu placeholder for show_placeholder_menu.
        """
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
        if input_str.startswith("?"):
            return True, input_str[1:].strip()
        return False, input_str.strip()

    async def get_command(
        self, raw_choices: str, from_validate=False
    ) -> tuple[bool, Command | None, tuple, dict[str, Any]]:
        """
        Returns the selected command based on user input.
        Supports keys, aliases, and abbreviations.
        """
        args = ()
        kwargs: dict[str, Any] = {}
        try:
            choice, *input_args = shlex.split(raw_choices)
        except ValueError:
            return False, None, args, kwargs
        is_preview, choice = self.parse_preview_command(choice)
        if is_preview and not choice and self.help_command:
            is_preview = False
            choice = "?"
        elif is_preview and not choice:
            # No help (list) command enabled
            if not from_validate:
                self.console.print(
                    f"[{OneColors.DARK_RED}]❌ You must enter a command for preview mode."
                )
            return is_preview, None, args, kwargs

        choice = choice.upper()
        name_map = self._name_map
        run_command = None
        if name_map.get(choice):
            run_command = name_map[choice]
        else:
            prefix_matches = [
                cmd for key, cmd in name_map.items() if key.startswith(choice)
            ]
            if len(prefix_matches) == 1:
                run_command = prefix_matches[0]

        if run_command:
            if not from_validate:
                logger.info("Command '%s' selected.", run_command.key)
            if is_preview:
                return True, run_command, args, kwargs
            elif self.is_cli_mode:
                return False, run_command, args, kwargs
            try:
                args, kwargs = await run_command.parse_args(input_args, from_validate)
            except (CommandArgumentError, Exception) as error:
                if not from_validate:
                    run_command.render_help()
                    self.console.print(
                        f"[{OneColors.DARK_RED}]❌ [{run_command.key}]: {error}"
                    )
                else:
                    raise ValidationError(
                        message=str(error), cursor_position=len(raw_choices)
                    )
                return is_preview, None, args, kwargs
            except HelpSignal:
                return True, None, args, kwargs
            return is_preview, run_command, args, kwargs

        fuzzy_matches = get_close_matches(choice, list(name_map.keys()), n=3, cutoff=0.7)
        if fuzzy_matches:
            if not from_validate:
                self.console.print(
                    f"[{OneColors.LIGHT_YELLOW}]⚠️ Unknown command '{choice}'. "
                    "Did you mean:"
                )
                for match in fuzzy_matches:
                    cmd = name_map[match]
                    self.console.print(f"  • [bold]{match}[/] → {cmd.description}")
            else:
                raise ValidationError(
                    message=f"Unknown command '{choice}'. Did you mean: "
                    f"{', '.join(fuzzy_matches)}?",
                    cursor_position=len(raw_choices),
                )
        else:
            if not from_validate:
                self.console.print(
                    f"[{OneColors.LIGHT_YELLOW}]⚠️ Unknown command '{choice}'[/]"
                )
            else:
                raise ValidationError(
                    message=f"Unknown command '{choice}'.",
                    cursor_position=len(raw_choices),
                )
        return is_preview, None, args, kwargs

    def _create_context(
        self, selected_command: Command, args: tuple, kwargs: dict[str, Any]
    ) -> ExecutionContext:
        """Creates an ExecutionContext object for the selected command."""
        return ExecutionContext(
            name=selected_command.description,
            args=args,
            kwargs=kwargs,
            action=selected_command,
        )

    async def _handle_action_error(
        self, selected_command: Command, error: Exception
    ) -> None:
        """Handles errors that occur during the action of the selected command."""
        logger.debug(
            "[%s] '%s' failed with error: %s",
            selected_command.key,
            selected_command.description,
            error,
            exc_info=True,
        )
        self.console.print(
            f"[{OneColors.DARK_RED}]An error occurred while executing "
            f"{selected_command.description}:[/] {error}"
        )

    async def process_command(self) -> bool:
        """Processes the action of the selected command."""
        app = get_app()
        await asyncio.sleep(0.1)
        app.invalidate()
        with patch_stdout(raw=True):
            choice = await self.prompt_session.prompt_async()
        is_preview, selected_command, args, kwargs = await self.get_command(choice)
        if not selected_command:
            logger.info("Invalid command '%s'.", choice)
            return True

        if is_preview:
            logger.info("Preview command '%s' selected.", selected_command.key)
            await selected_command.preview()
            return True

        self.last_run_command = selected_command

        if selected_command == self.exit_command:
            logger.info("Back selected: exiting %s", self.get_title())
            return False

        context = self._create_context(selected_command, args, kwargs)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            result = await selected_command(*args, **kwargs)
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            await self._handle_action_error(selected_command, error)
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
        return True

    async def run_key(
        self,
        command_key: str,
        return_context: bool = False,
        args: tuple = (),
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Run a command by key without displaying the menu (non-interactive mode)."""
        self.debug_hooks()
        is_preview, selected_command, _, __ = await self.get_command(command_key)
        kwargs = kwargs or {}

        self.last_run_command = selected_command

        if not selected_command:
            return None

        if is_preview:
            logger.info("Preview command '%s' selected.", selected_command.key)
            await selected_command.preview()
            return None

        logger.info(
            "[run_key] Executing: %s — %s",
            selected_command.key,
            selected_command.description,
        )

        context = self._create_context(selected_command, args, kwargs)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            result = await selected_command(*args, **kwargs)
            context.result = result

            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            logger.info("[run_key] '%s' complete.", selected_command.description)
        except (KeyboardInterrupt, EOFError) as error:
            logger.warning(
                "[run_key] Interrupted by user: %s", selected_command.description
            )
            raise FalyxError(
                f"[run_key] ⚠️ '{selected_command.description}' interrupted by user."
            ) from error
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            await self._handle_action_error(selected_command, error)
            raise FalyxError(
                f"[run_key] ❌ '{selected_command.description}' failed."
            ) from error
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)

        return context if return_context else context.result

    def _set_retry_policy(self, selected_command: Command) -> None:
        """Sets the retry policy for the command based on CLI arguments."""
        assert isinstance(self.cli_args, Namespace), "CLI arguments must be provided."
        if (
            self.cli_args.retries
            or self.cli_args.retry_delay
            or self.cli_args.retry_backoff
        ):
            selected_command.retry_policy.enabled = True
            if self.cli_args.retries:
                selected_command.retry_policy.max_retries = self.cli_args.retries
            if self.cli_args.retry_delay:
                selected_command.retry_policy.delay = self.cli_args.retry_delay
            if self.cli_args.retry_backoff:
                selected_command.retry_policy.backoff = self.cli_args.retry_backoff
            if isinstance(selected_command.action, Action):
                selected_command.action.set_retry_policy(selected_command.retry_policy)
            else:
                logger.warning(
                    "[Command:%s] Retry requested, but action is not an Action instance.",
                    selected_command.key,
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
        self.debug_hooks()
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
                    task = asyncio.create_task(self.process_command())
                    should_continue = await task
                    if not should_continue:
                        break
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
        finally:
            logger.info("Exiting menu: %s", self.get_title())
            if self.exit_message:
                self.print_message(self.exit_message)

    async def run(
        self,
        falyx_parsers: FalyxParsers | None = None,
        root_parser: ArgumentParser | None = None,
        subparsers: _SubParsersAction | None = None,
        callback: Callable[..., Any] | None = None,
    ) -> None:
        """
        Entrypoint for executing a Falyx CLI application via structured subcommands.

        This method parses CLI arguments, configures the runtime environment, and dispatches
        execution to the appropriate command mode:

        - help - Show help output, optionally filtered by tag.
        - version - Print the program version and exit.
        - preview - Display a preview of the specified command without executing it.
        - run - Execute a single command with parsed arguments and lifecycle hooks.
        - run-all - Run all commands matching a tag concurrently (with default args).
        - (default) - Launch the interactive Falyx menu loop.

        It also applies CLI flags such as `--verbose`, `--debug-hooks`, and summary reporting,
        and supports an optional callback for post-parse setup.

        Args:
            falyx_parsers (FalyxParsers | None):
                Preconfigured argument parser set. If not provided, a default parser
                is created using the registered commands and passed-in `root_parser`
                or `subparsers`.
            root_parser (ArgumentParser | None):
                Optional root parser to merge into the CLI (used if `falyx_parsers`
                is not supplied).
            subparsers (_SubParsersAction | None):
                Optional subparser group to extend (used if `falyx_parsers` is not supplied).
            callback (Callable[..., Any] | None):
                An optional function or coroutine to run after parsing CLI arguments,
                typically for initializing logging, environment setup, or other
                pre-execution configuration.

        Raises:
            FalyxError:
                If invalid parser objects are supplied, or CLI arguments conflict
                with the expected run mode.
            SystemExit:
                Exits with an appropriate exit code based on the selected command
                or signal (e.g. Ctrl+C triggers exit code 130).

        Notes:
            - `run-all` executes all tagged commands **in parallel** and does not
            supply arguments to individual commands; use `ChainedAction` or explicit
            CLI calls for ordered or parameterized workflows.
            - Most CLI commands exit the process via `sys.exit()` after completion.
            - For interactive sessions, this method falls back to `menu()`.

        Example:
            ```
            >>> flx = Falyx()
            >>> await flx.run()   # Parses CLI args and dispatches appropriately
            ```
        """

        if self.cli_args:
            raise FalyxError(
                "Run is incompatible with CLI arguments. Use 'run_key' instead."
            )
        if falyx_parsers:
            if not isinstance(falyx_parsers, FalyxParsers):
                raise FalyxError("falyx_parsers must be an instance of FalyxParsers.")
        else:
            falyx_parsers = get_arg_parsers(
                self.program,
                self.usage,
                self.description,
                self.epilog,
                commands=self.commands,
                root_parser=root_parser,
                subparsers=subparsers,
            )
        self.cli_args = falyx_parsers.parse_args()
        self.options.from_namespace(self.cli_args, "cli_args")

        if callback:
            if not callable(callback):
                raise FalyxError("Callback must be a callable function.")
            async_callback = ensure_async(callback)
            await async_callback(self.cli_args)

        if not self.options.get("never_prompt"):
            self.options.set("never_prompt", self._never_prompt)

        if not self.options.get("force_confirm"):
            self.options.set("force_confirm", self._force_confirm)

        if not self.options.get("hide_menu_table"):
            self.options.set("hide_menu_table", self._hide_menu_table)

        if self.cli_args.verbose:
            logging.getLogger("falyx").setLevel(logging.DEBUG)

        if self.cli_args.debug_hooks:
            logger.debug("Enabling global debug hooks for all commands")
            self.register_all_with_debug_hooks()

        if self.cli_args.command == "help":
            self.options.set("mode", FalyxMode.HELP)
            await self._render_help(
                tag=self.cli_args.tag, key=self.cli_args.key, tldr=self.cli_args.tldr
            )
            sys.exit(0)

        if self.cli_args.command == "version" or self.cli_args.version:
            self.console.print(f"[{self.version_style}]{self.program} v{self.version}[/]")
            sys.exit(0)

        if self.cli_args.command == "preview":
            self.options.set("mode", FalyxMode.PREVIEW)
            _, command, args, kwargs = await self.get_command(self.cli_args.name)
            if not command:
                self.console.print(
                    f"[{OneColors.DARK_RED}]❌ Command '{self.cli_args.name}' not found."
                )
                sys.exit(1)
            self.console.print(
                f"Preview of command '{command.key}': {command.description}"
            )
            await command.preview()
            sys.exit(0)

        if self.cli_args.command == "run":
            self.options.set("mode", FalyxMode.RUN)
            is_preview, command, _, __ = await self.get_command(self.cli_args.name)
            if is_preview:
                if command is None:
                    sys.exit(1)
                logger.info("Preview command '%s' selected.", command.key)
                await command.preview()
                sys.exit(0)
            if not command:
                sys.exit(1)
            self._set_retry_policy(command)
            try:
                args, kwargs = await command.parse_args(self.cli_args.command_args)
            except HelpSignal:
                sys.exit(0)
            except CommandArgumentError as error:
                self.console.print(f"[{OneColors.DARK_RED}]❌ ['{command.key}'] {error}")
                command.render_help()
                sys.exit(1)
            try:
                await self.run_key(self.cli_args.name, args=args, kwargs=kwargs)
            except FalyxError as error:
                self.console.print(f"[{OneColors.DARK_RED}]❌ Error: {error}[/]")
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

            if self.cli_args.summary:
                er.summary()
            sys.exit(0)

        if self.cli_args.command == "run-all":
            self.options.set("mode", FalyxMode.RUN_ALL)
            matching = [
                cmd
                for cmd in self.commands.values()
                if self.cli_args.tag.lower() in (tag.lower() for tag in cmd.tags)
            ]
            if not matching:
                self.console.print(
                    f"[{OneColors.LIGHT_YELLOW}]⚠️ No commands found with tag: "
                    f"'{self.cli_args.tag}'"
                )
                sys.exit(1)

            self.console.print(
                f"[{OneColors.CYAN_b}]🚀 Running all commands with tag:[/] "
                f"{self.cli_args.tag}"
            )

            tasks = []
            try:
                for cmd in matching:
                    self._set_retry_policy(cmd)
                    tasks.append(self.run_key(cmd.key))
            except Exception as error:
                self.console.print(
                    f"[{OneColors.DARK_RED}]❌ Unexpected error: {error}[/]"
                )
                sys.exit(1)

            had_errors = False
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, QuitSignal):
                    logger.info("[QuitSignal]. <- Exiting run.")
                    sys.exit(130)
                elif isinstance(result, CancelSignal):
                    logger.info("[CancelSignal]. <- Execution cancelled.")
                    sys.exit(1)
                elif isinstance(result, BackSignal):
                    logger.info("[BackSignal]. <- Back signal received.")
                    sys.exit(1)
                elif isinstance(result, FalyxError):
                    self.console.print(f"[{OneColors.DARK_RED}]❌ Error: {result}[/]")
                    had_errors = True

            if had_errors:
                sys.exit(1)

            if self.cli_args.summary:
                er.summary()

            sys.exit(0)

        await self.menu()
