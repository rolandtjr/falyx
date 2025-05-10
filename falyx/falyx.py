# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""falyx.py

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
import asyncio
import logging
import sys
from argparse import Namespace
from difflib import get_close_matches
from enum import Enum
from functools import cached_property
from typing import Any, Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.validation import Validator
from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from falyx.action import Action, BaseAction
from falyx.bottom_bar import BottomBar
from falyx.command import Command
from falyx.context import ExecutionContext
from falyx.debug import log_after, log_before, log_error, log_success
from falyx.exceptions import (
    CommandAlreadyExistsError,
    FalyxError,
    InvalidActionError,
    NotAFalyxError,
)
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.options_manager import OptionsManager
from falyx.parsers import get_arg_parsers
from falyx.retry import RetryPolicy
from falyx.signals import BackSignal, QuitSignal
from falyx.themes.colors import OneColors, get_nord_theme
from falyx.utils import CaseInsensitiveDict, chunks, get_program_invocation, logger
from falyx.version import __version__


class FalyxMode(str, Enum):
    MENU = "menu"
    RUN = "run"
    PREVIEW = "preview"
    RUN_ALL = "run-all"


class Falyx:
    """
    Main menu controller for Falyx CLI applications.

    Falyx orchestrates the full lifecycle of an interactive menu system,
    handling user input, command execution, error recovery, and structured
    CLI workflows.

    Key Features:
    - Interactive menu with Rich rendering and Prompt Toolkit input handling
    - Dynamic command management with alias and abbreviation matching
    - Full lifecycle hooks (before, success, error, after, teardown) at both menu and command levels
    - Built-in retry support, spinner visuals, and confirmation prompts
    - Submenu nesting and action chaining
    - History tracking, help generation, and run key execution modes
    - Seamless CLI argument parsing and integration via argparse
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
        options (OptionsManager | None): Declarative option mappings.
        custom_table (Callable[[Falyx], Table] | Table | None): Custom menu table generator.

    Methods:
        run(): Main entry point for CLI argument-based workflows. Most users will use this.
        menu(): Run the interactive menu loop.
        run_key(command_key, return_context): Run a command directly without showing the menu.
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
        prompt: str | AnyFormattedText = "> ",
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
        render_menu: Callable[["Falyx"], None] | None = None,
        custom_table: Callable[["Falyx"], Table] | Table | None = None,
    ) -> None:
        """Initializes the Falyx object."""
        self.title: str | Markdown = title
        self.prompt: str | AnyFormattedText = prompt
        self.columns: int = columns
        self.commands: dict[str, Command] = CaseInsensitiveDict()
        self.exit_command: Command = self._get_exit_command()
        self.history_command: Command | None = (
            self._get_history_command() if include_history_command else None
        )
        self.help_command: Command | None = (
            self._get_help_command() if include_help_command else None
        )
        self.console: Console = Console(color_system="auto", theme=get_nord_theme())
        self.welcome_message: str | Markdown | dict[str, Any] = welcome_message
        self.exit_message: str | Markdown | dict[str, Any] = exit_message
        self.hooks: HookManager = HookManager()
        self.last_run_command: Command | None = None
        self.key_bindings: KeyBindings = key_bindings or KeyBindings()
        self.bottom_bar: BottomBar | str | Callable[[], None] = bottom_bar
        self._never_prompt: bool = never_prompt
        self._force_confirm: bool = force_confirm
        self.cli_args: Namespace | None = cli_args
        self.render_menu: Callable[["Falyx"], None] | None = render_menu
        self.custom_table: Callable[["Falyx"], Table] | Table | None = custom_table
        self.validate_options(cli_args, options)
        self._prompt_session: PromptSession | None = None
        self.mode = FalyxMode.MENU

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
        """Builds a mapping of all valid input names (keys, aliases, normalized names) to Command objects.
        If a collision occurs, logs a warning and keeps the first registered command.
        """
        mapping: dict[str, Command] = {}

        def register(name: str, cmd: Command):
            norm = name.upper().strip()
            if norm in mapping:
                existing = mapping[norm]
                if existing is not cmd:
                    logger.warning(
                        f"[alias conflict] '{name}' already assigned to '{existing.description}'."
                        f" Skipping for '{cmd.description}'."
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
            key="Q",
            description="Exit",
            aliases=["EXIT", "QUIT"],
            style=OneColors.DARK_RED,
        )

    def _get_history_command(self) -> Command:
        """Returns the history command for the menu."""
        return Command(
            key="Y",
            description="History",
            aliases=["HISTORY"],
            action=er.get_history_action(),
            style=OneColors.DARK_YELLOW,
        )

    async def _show_help(self):
        table = Table(title="[bold cyan]Help Menu[/]", box=box.SIMPLE)
        table.add_column("Key", style="bold", no_wrap=True)
        table.add_column("Aliases", style="dim", no_wrap=True)
        table.add_column("Description", style="dim", overflow="fold")
        table.add_column("Tags", style="dim", no_wrap=True)

        for command in self.commands.values():
            help_text = command.help_text or command.description
            if command.requires_input:
                help_text += " [dim](requires input)[/dim]"
            table.add_row(
                f"[{command.style}]{command.key}[/]",
                ", ".join(command.aliases) if command.aliases else "None",
                help_text,
                ", ".join(command.tags) if command.tags else "None",
            )

        table.add_row(
            f"[{self.exit_command.style}]{self.exit_command.key}[/]",
            ", ".join(self.exit_command.aliases),
            "Exit this menu or program",
        )

        if self.history_command:
            table.add_row(
                f"[{self.history_command.style}]{self.history_command.key}[/]",
                ", ".join(self.history_command.aliases),
                "History of executed actions",
            )

        if self.help_command:
            table.add_row(
                f"[{self.help_command.style}]{self.help_command.key}[/]",
                ", ".join(self.help_command.aliases),
                "Show this help menu",
            )

        self.console.print(table, justify="center")
        if self.mode == FalyxMode.MENU:
            self.console.print(
                f"📦 Tip: '[{OneColors.LIGHT_YELLOW}]?[KEY][/]' to preview a command before running it.\n",
                justify="center",
            )

    def _get_help_command(self) -> Command:
        """Returns the help command for the menu."""
        return Command(
            key="H",
            aliases=["HELP"],
            description="Help",
            action=self._show_help,
            style=OneColors.LIGHT_YELLOW,
        )

    def _get_completer(self) -> WordCompleter:
        """Completer to provide auto-completion for the menu commands."""
        keys = [self.exit_command.key]
        keys.extend(self.exit_command.aliases)
        if self.history_command:
            keys.append(self.history_command.key)
            keys.extend(self.history_command.aliases)
        if self.help_command:
            keys.append(self.help_command.key)
            keys.extend(self.help_command.aliases)
        for cmd in self.commands.values():
            keys.append(cmd.key)
            keys.extend(cmd.aliases)
        return WordCompleter(keys, ignore_case=True)

    def _get_validator(self) -> Validator:
        """Validator to check if the input is a valid command or toggle key."""
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

        if isinstance(self._bottom_bar, BottomBar):
            toggle_keys = {key.upper() for key in self._bottom_bar.toggle_keys}
        else:
            toggle_keys = set()

        commands_str = ", ".join(sorted(keys))
        toggles_str = ", ".join(sorted(toggle_keys))

        message_lines = ["Invalid input. Available keys:"]
        if keys:
            message_lines.append(f"  Commands: {commands_str}")
        if toggle_keys:
            message_lines.append(f"  Toggles: {toggles_str}")
        error_message = " ".join(message_lines)

        def validator(text):
            is_preview, choice = self.get_command(text, from_validate=True)
            if is_preview and choice is None:
                return True
            return True if choice else False

        return Validator.from_callable(
            validator,
            error_message=error_message,
            move_cursor_to_end=True,
        )

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
                self.columns, self.key_bindings, key_validator=self.is_key_available
            )
        elif isinstance(bottom_bar, BottomBar):
            bottom_bar.key_validator = self.is_key_available
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
            self._prompt_session = PromptSession(
                message=self.prompt,
                multiline=False,
                completer=self._get_completer(),
                reserve_space_for_menu=1,
                validator=self._get_validator(),
                bottom_toolbar=self._get_bottom_bar_render(),
                key_bindings=self.key_bindings,
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

        def hook_names(hook_list):
            return [hook.__name__ for hook in hook_list]

        logger.debug(
            "Menu-level before hooks: "
            f"{hook_names(self.hooks._hooks[HookType.BEFORE])}"
        )
        logger.debug(
            f"Menu-level success hooks: {hook_names(self.hooks._hooks[HookType.ON_SUCCESS])}"
        )
        logger.debug(
            f"Menu-level error hooks: {hook_names(self.hooks._hooks[HookType.ON_ERROR])}"
        )
        logger.debug(
            f"Menu-level after hooks: {hook_names(self.hooks._hooks[HookType.AFTER])}"
        )
        logger.debug(
            f"Menu-level on_teardown hooks: {hook_names(self.hooks._hooks[HookType.ON_TEARDOWN])}"
        )

        for key, command in self.commands.items():
            logger.debug(
                f"[Command '{key}'] before: {hook_names(command.hooks._hooks[HookType.BEFORE])}"
            )
            logger.debug(
                f"[Command '{key}'] success: {hook_names(command.hooks._hooks[HookType.ON_SUCCESS])}"
            )
            logger.debug(
                f"[Command '{key}'] error: {hook_names(command.hooks._hooks[HookType.ON_ERROR])}"
            )
            logger.debug(
                f"[Command '{key}'] after: {hook_names(command.hooks._hooks[HookType.AFTER])}"
            )
            logger.debug(
                f"[Command '{key}'] on_teardown: {hook_names(command.hooks._hooks[HookType.ON_TEARDOWN])}"
            )

    def is_key_available(self, key: str) -> bool:
        key = key.upper()
        toggles = (
            self._bottom_bar.toggle_keys
            if isinstance(self._bottom_bar, BottomBar)
            else []
        )

        conflicts = (
            key in self.commands,
            key == self.exit_command.key.upper(),
            self.history_command and key == self.history_command.key.upper(),
            self.help_command and key == self.help_command.key.upper(),
            key in toggles,
        )

        return not any(conflicts)

    def _validate_command_key(self, key: str) -> None:
        """Validates the command key to ensure it is unique."""
        key = key.upper()
        toggles = (
            self._bottom_bar.toggle_keys
            if isinstance(self._bottom_bar, BottomBar)
            else []
        )
        collisions = []

        if key in self.commands:
            collisions.append("command")
        if key == self.exit_command.key.upper():
            collisions.append("back command")
        if self.history_command and key == self.history_command.key.upper():
            collisions.append("history command")
        if self.help_command and key == self.help_command.key.upper():
            collisions.append("help command")
        if key in toggles:
            collisions.append("toggle")

        if collisions:
            raise CommandAlreadyExistsError(
                f"Command key '{key}' conflicts with existing {', '.join(collisions)}."
            )

    def update_exit_command(
        self,
        key: str = "Q",
        description: str = "Exit",
        aliases: list[str] | None = None,
        action: Callable[[], Any] = lambda: None,
        style: str = OneColors.DARK_RED,
        confirm: bool = False,
        confirm_message: str = "Are you sure?",
    ) -> None:
        """Updates the back command of the menu."""
        if not callable(action):
            raise InvalidActionError("Action must be a callable.")
        self._validate_command_key(key)
        self.exit_command = Command(
            key=key,
            description=description,
            aliases=aliases if aliases else self.exit_command.aliases,
            action=action,
            style=style,
            confirm=confirm,
            confirm_message=confirm_message,
        )

    def add_submenu(
        self, key: str, description: str, submenu: "Falyx", *, style: str = OneColors.CYAN
    ) -> None:
        """Adds a submenu to the menu."""
        if not isinstance(submenu, Falyx):
            raise NotAFalyxError("submenu must be an instance of Falyx.")
        self._validate_command_key(key)
        self.add_command(key, description, submenu.menu, style=style)
        submenu.update_exit_command(key="B", description="Back", aliases=["BACK"])

    def add_commands(self, commands: list[dict]) -> None:
        """Adds multiple commands to the menu."""
        for command in commands:
            self.add_command(**command)

    def add_command(
        self,
        key: str,
        description: str,
        action: BaseAction | Callable[[], Any],
        *,
        args: tuple = (),
        kwargs: dict[str, Any] = {},
        hidden: bool = False,
        aliases: list[str] | None = None,
        help_text: str = "",
        style: str = OneColors.WHITE,
        confirm: bool = False,
        confirm_message: str = "Are you sure?",
        preview_before_confirm: bool = True,
        spinner: bool = False,
        spinner_message: str = "Processing...",
        spinner_type: str = "dots",
        spinner_style: str = OneColors.CYAN,
        spinner_kwargs: dict[str, Any] | None = None,
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
        requires_input: bool | None = None,
    ) -> Command:
        """Adds an command to the menu, preventing duplicates."""
        self._validate_command_key(key)
        command = Command(
            key=key,
            description=description,
            action=action,
            args=args,
            kwargs=kwargs,
            hidden=hidden,
            aliases=aliases if aliases else [],
            help_text=help_text,
            style=style,
            confirm=confirm,
            confirm_message=confirm_message,
            preview_before_confirm=preview_before_confirm,
            spinner=spinner,
            spinner_message=spinner_message,
            spinner_type=spinner_type,
            spinner_style=spinner_style,
            spinner_kwargs=spinner_kwargs or {},
            tags=tags if tags else [],
            logging_hooks=logging_hooks,
            retry=retry,
            retry_all=retry_all,
            retry_policy=retry_policy or RetryPolicy(),
            requires_input=requires_input,
            options_manager=self.options,
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

        self.commands[key] = command
        return command

    def get_bottom_row(self) -> list[str]:
        """Returns the bottom row of the table for displaying additional commands."""
        bottom_row = []
        if self.history_command:
            bottom_row.append(
                f"[{self.history_command.key}] [{self.history_command.style}]{self.history_command.description}"
            )
        if self.help_command:
            bottom_row.append(
                f"[{self.help_command.key}] [{self.help_command.style}]{self.help_command.description}"
            )
        bottom_row.append(
            f"[{self.exit_command.key}] [{self.exit_command.style}]{self.exit_command.description}"
        )
        return bottom_row

    def build_default_table(self) -> Table:
        """Build the standard table layout. Developers can subclass or call this in custom tables."""
        table = Table(title=self.title, show_header=False, box=box.SIMPLE, expand=True)
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

    @property
    def table(self) -> Table:
        """Creates or returns a custom table to display the menu commands."""
        if callable(self.custom_table):
            return self.custom_table(self)
        elif isinstance(self.custom_table, Table):
            return self.custom_table
        else:
            return self.build_default_table()

    def parse_preview_command(self, input_str: str) -> tuple[bool, str]:
        if input_str.startswith("?"):
            return True, input_str[1:].strip()
        return False, input_str.strip()

    def get_command(
        self, choice: str, from_validate=False
    ) -> tuple[bool, Command | None]:
        """Returns the selected command based on user input. Supports keys, aliases, and abbreviations."""
        is_preview, choice = self.parse_preview_command(choice)
        if is_preview and not choice:
            if not from_validate:
                self.console.print(
                    f"[{OneColors.DARK_RED}]❌ You must enter a command for preview mode.[/]"
                )
            return is_preview, None

        choice = choice.upper()
        name_map = self._name_map

        if choice in name_map:
            return is_preview, name_map[choice]

        prefix_matches = [cmd for key, cmd in name_map.items() if key.startswith(choice)]
        if len(prefix_matches) == 1:
            return is_preview, prefix_matches[0]

        fuzzy_matches = get_close_matches(choice, list(name_map.keys()), n=3, cutoff=0.7)
        if fuzzy_matches:
            if not from_validate:
                self.console.print(
                    f"[{OneColors.LIGHT_YELLOW}]⚠️ Unknown command '{choice}'. Did you mean:[/] "
                )
            for match in fuzzy_matches:
                cmd = name_map[match]
                self.console.print(f"  • [bold]{match}[/] → {cmd.description}")
        else:
            if not from_validate:
                self.console.print(
                    f"[{OneColors.LIGHT_YELLOW}]⚠️ Unknown command '{choice}'[/]"
                )
        return is_preview, None

    def _create_context(self, selected_command: Command) -> ExecutionContext:
        """Creates a context dictionary for the selected command."""
        return ExecutionContext(
            name=selected_command.description,
            args=tuple(),
            kwargs={},
            action=selected_command,
        )

    async def _handle_action_error(
        self, selected_command: Command, error: Exception
    ) -> None:
        """Handles errors that occur during the action of the selected command."""
        logger.exception(f"Error executing '{selected_command.description}': {error}")
        self.console.print(
            f"[{OneColors.DARK_RED}]An error occurred while executing "
            f"{selected_command.description}:[/] {error}"
        )

    async def process_command(self) -> bool:
        """Processes the action of the selected command."""
        choice = await self.prompt_session.prompt_async()
        is_preview, selected_command = self.get_command(choice)
        if not selected_command:
            logger.info(f"Invalid command '{choice}'.")
            return True

        if is_preview:
            logger.info(f"Preview command '{selected_command.key}' selected.")
            await selected_command.preview()
            return True

        if selected_command.requires_input:
            program = get_program_invocation()
            self.console.print(
                f"[{OneColors.LIGHT_YELLOW}]⚠️ Command '{selected_command.key}' requires input "
                f"and must be run via [{OneColors.MAGENTA}]'{program} run'[{OneColors.LIGHT_YELLOW}] "
                "with proper piping or arguments.[/]"
            )
            return True

        self.last_run_command = selected_command

        if selected_command == self.exit_command:
            logger.info(f"🔙 Back selected: exiting {self.get_title()}")
            return False

        context = self._create_context(selected_command)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            result = await selected_command()
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

    async def run_key(self, command_key: str, return_context: bool = False) -> Any:
        """Run a command by key without displaying the menu (non-interactive mode)."""
        self.debug_hooks()
        is_preview, selected_command = self.get_command(command_key)
        self.last_run_command = selected_command

        if not selected_command:
            return None

        if is_preview:
            logger.info(f"Preview command '{selected_command.key}' selected.")
            await selected_command.preview()
            return None

        logger.info(
            "[run_key] 🚀 Executing: %s — %s",
            selected_command.key,
            selected_command.description,
        )

        context = self._create_context(selected_command)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)
            result = await selected_command()
            context.result = result

            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            logger.info("[run_key] ✅ '%s' complete.", selected_command.description)
        except (KeyboardInterrupt, EOFError):
            logger.warning(
                "[run_key] ⚠️ Interrupted by user: ", selected_command.description
            )
            raise FalyxError(
                f"[run_key] ⚠️ '{selected_command.description}' interrupted by user."
            )
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            logger.error(
                "[run_key] ❌ Failed: %s — %s: %s",
                selected_command.description,
                type(error).__name__,
                error,
            )
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
                    f"[Command:{selected_command.key}] Retry requested, but action is not an Action instance."
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
        logger.info(f"Running menu: {self.get_title()}")
        self.debug_hooks()
        if self.welcome_message:
            self.print_message(self.welcome_message)
        while True:
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
                logger.info("QuitSignal received. Exiting menu.")
                break
            except BackSignal:
                logger.info("BackSignal received.")
            finally:
                logger.info(f"Exiting menu: {self.get_title()}")
                if self.exit_message:
                    self.print_message(self.exit_message)

    async def run(self) -> None:
        """Run Falyx CLI with structured subcommands."""
        if not self.cli_args:
            self.cli_args = get_arg_parsers().root.parse_args()
        self.options.from_namespace(self.cli_args, "cli_args")

        if not self.options.get("never_prompt"):
            self.options.set("never_prompt", self._never_prompt)

        if not self.options.get("force_confirm"):
            self.options.set("force_confirm", self._force_confirm)

        if self.cli_args.verbose:
            logging.getLogger("falyx").setLevel(logging.DEBUG)

        if self.cli_args.debug_hooks:
            logger.debug("✅ Enabling global debug hooks for all commands")
            self.register_all_with_debug_hooks()

        if self.cli_args.command == "list":
            await self._show_help()
            sys.exit(0)

        if self.cli_args.command == "version" or self.cli_args.version:
            self.console.print(f"[{OneColors.GREEN_b}]Falyx CLI v{__version__}[/]")
            sys.exit(0)

        if self.cli_args.command == "preview":
            self.mode = FalyxMode.PREVIEW
            _, command = self.get_command(self.cli_args.name)
            if not command:
                self.console.print(
                    f"[{OneColors.DARK_RED}]❌ Command '{self.cli_args.name}' not found.[/]"
                )
                sys.exit(1)
            self.console.print(
                f"Preview of command '{command.key}': {command.description}"
            )
            await command.preview()
            sys.exit(0)

        if self.cli_args.command == "run":
            self.mode = FalyxMode.RUN
            is_preview, command = self.get_command(self.cli_args.name)
            if is_preview:
                if command is None:
                    sys.exit(1)
                logger.info(f"Preview command '{command.key}' selected.")
                await command.preview()
                sys.exit(0)
            if not command:
                sys.exit(1)
            self._set_retry_policy(command)
            try:
                await self.run_key(self.cli_args.name)
            except FalyxError as error:
                self.console.print(f"[{OneColors.DARK_RED}]❌ Error: {error}[/]")
                sys.exit(1)

            if self.cli_args.summary:
                er.summary()
            sys.exit(0)

        if self.cli_args.command == "run-all":
            self.mode = FalyxMode.RUN_ALL
            matching = [
                cmd
                for cmd in self.commands.values()
                if self.cli_args.tag.lower() in (tag.lower() for tag in cmd.tags)
            ]
            if not matching:
                self.console.print(
                    f"[{OneColors.LIGHT_YELLOW}]⚠️ No commands found with tag: '{self.cli_args.tag}'[/]"
                )
                sys.exit(1)

            self.console.print(
                f"[{OneColors.CYAN_b}]🚀 Running all commands with tag:[/] {self.cli_args.tag}"
            )
            for cmd in matching:
                self._set_retry_policy(cmd)
                await self.run_key(cmd.key)

            if self.cli_args.summary:
                er.summary()

            sys.exit(0)

        await self.menu()
