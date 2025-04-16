"""falyx.py

This class creates a Falyx object that creates a selectable menu
with customizable commands and functionality.

It allows for adding commands, and their accompanying actions,
and provides a method to display the menu and handle user input.

This class uses the `rich` library to display the menu in a
formatted and visually appealing way.

This class also uses the `prompt_toolkit` library to handle
user input and create an interactive experience.
"""
import asyncio
import logging
import sys
from argparse import ArgumentParser, Namespace
from difflib import get_close_matches
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

from falyx.action import BaseAction
from falyx.bottom_bar import BottomBar
from falyx.command import Command
from falyx.context import ExecutionContext
from falyx.debug import log_after, log_before, log_error, log_success
from falyx.exceptions import (CommandAlreadyExistsError, FalyxError,
                              InvalidActionError, NotAFalyxError)
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import Hook, HookManager, HookType
from falyx.retry import RetryPolicy
from falyx.themes.colors import OneColors, get_nord_theme
from falyx.utils import CaseInsensitiveDict, async_confirm, chunks, logger
from falyx.version import __version__


class Falyx:
    """Class to create a menu with commands.

    Hook functions must have the signature:
        def hook(command: Command) -> None:
    where `command` is the selected command.

    Error hook functions must have the signature:
        def error_hook(command: Command, error: Exception) -> None:
    where `command` is the selected command and `error` is the exception raised.

    Hook execution order:
    1. Before action hooks of the menu.
    2. Before action hooks of the selected command.
    3. Action of the selected command.
    4. After action hooks of the selected command.
    5. After action hooks of the menu.
    6. On error hooks of the selected command (if an error occurs).
    7. On error hooks of the menu (if an error occurs).

    Parameters:
        title (str|Markdown): The title of the menu.
        columns (int): The number of columns to display the commands in.
        prompt (AnyFormattedText): The prompt to display when asking for input.
        bottom_bar (str|callable|None): The text to display in the bottom bar.
    """

    def __init__(
        self,
        title: str | Markdown = "Menu",
        prompt: str | AnyFormattedText = "> ",
        columns: int = 3,
        bottom_bar: BottomBar | str | Callable[[], None] | None = None,
        welcome_message: str | Markdown = "",
        exit_message: str | Markdown = "",
        key_bindings: KeyBindings | None = None,
        include_history_command: bool = True,
        include_help_command: bool = False,
        confirm_on_error: bool = True,
        never_confirm: bool = False,
        always_confirm: bool = False,
        cli_args: Namespace | None = None,
        custom_table: Callable[["Falyx"], Table] | Table | None = None,
    ) -> None:
        """Initializes the Falyx object."""
        self.title: str | Markdown = title
        self.prompt: str | AnyFormattedText = prompt
        self.columns: int = columns
        self.commands: dict[str, Command] = CaseInsensitiveDict()
        self.exit_command: Command = self._get_exit_command()
        self.history_command: Command | None = self._get_history_command() if include_history_command else None
        self.help_command: Command | None = self._get_help_command() if include_help_command else None
        self.console: Console = Console(color_system="truecolor", theme=get_nord_theme())
        self.welcome_message: str | Markdown = welcome_message
        self.exit_message: str | Markdown = exit_message
        self.hooks: HookManager = HookManager()
        self.last_run_command: Command | None = None
        self.key_bindings: KeyBindings = key_bindings or KeyBindings()
        self.bottom_bar: BottomBar | str | Callable[[], None] = bottom_bar or BottomBar(columns=columns, key_bindings=self.key_bindings)
        self.confirm_on_error: bool = confirm_on_error
        self._never_confirm: bool = never_confirm
        self._always_confirm: bool = always_confirm
        self.cli_args: Namespace | None = cli_args
        self.custom_table: Callable[["Falyx"], Table] | Table | None = custom_table

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
            color=OneColors.DARK_RED,
        )

    def _get_history_command(self) -> Command:
        """Returns the history command for the menu."""
        return Command(
            key="Y",
            description="History",
            aliases=["HISTORY"],
            action=er.get_history_action(),
            color=OneColors.DARK_YELLOW,
        )

    async def _show_help(self):
        table = Table(title="[bold cyan]Help Menu[/]", box=box.SIMPLE)
        table.add_column("Key", style="bold", no_wrap=True)
        table.add_column("Aliases", style="dim", no_wrap=True)
        table.add_column("Description", style="dim", overflow="fold")
        table.add_column("Tags", style="dim", no_wrap=True)

        for command in self.commands.values():
            help_text = command.help_text or command.description
            table.add_row(
                f"[{command.color}]{command.key}[/]",
                ", ".join(command.aliases) if command.aliases else "None",
                help_text,
                ", ".join(command.tags) if command.tags else "None"
            )

        table.add_row(
            f"[{self.exit_command.color}]{self.exit_command.key}[/]",
            ", ".join(self.exit_command.aliases),
            "Exit this menu or program"
        )

        if self.history_command:
            table.add_row(
                f"[{self.history_command.color}]{self.history_command.key}[/]",
                ", ".join(self.history_command.aliases),
                "History of executed actions"
        )

        if self.help_command:
            table.add_row(
                f"[{self.help_command.color}]{self.help_command.key}[/]",
                ", ".join(self.help_command.aliases),
                "Show this help menu"
            )

        self.console.print(table)

    def _get_help_command(self) -> Command:
        """Returns the help command for the menu."""
        return Command(
            key="H",
            aliases=["HELP"],
            description="Help",
            action=self._show_help,
            color=OneColors.LIGHT_YELLOW,
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

        if isinstance(self.bottom_bar, BottomBar):
            toggle_keys = {key.upper() for key in self.bottom_bar.toggles}
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
            return True if self.get_command(text, from_validate=True) else False

        return Validator.from_callable(
            validator,
            error_message=error_message,
            move_cursor_to_end=True,
        )

    def _invalidate_session_cache(self):
        """Forces the session to be recreated on the next access."""
        if hasattr(self, "session"):
            del self.session

    def add_toggle(self, key: str, label: str, state: bool) -> None:
        """Adds a toggle to the bottom bar."""
        assert isinstance(self.bottom_bar, BottomBar), "Bottom bar must be an instance of BottomBar."
        self.bottom_bar.add_toggle(key, label, state)
        self._invalidate_session_cache()

    def add_counter(self, name: str, label: str, current: int) -> None:
        """Adds a counter to the bottom bar."""
        assert isinstance(self.bottom_bar, BottomBar), "Bottom bar must be an instance of BottomBar."
        self.bottom_bar.add_counter(name, label, current)
        self._invalidate_session_cache()

    def add_total_counter(self, name: str, label: str, current: int, total: int) -> None:
        """Adds a counter to the bottom bar."""
        assert isinstance(self.bottom_bar, BottomBar), "Bottom bar must be an instance of BottomBar."
        self.bottom_bar.add_total_counter(name, label, current, total)
        self._invalidate_session_cache()

    def add_static(self, name: str, text: str) -> None:
        """Adds a static element to the bottom bar."""
        assert isinstance(self.bottom_bar, BottomBar), "Bottom bar must be an instance of BottomBar."
        self.bottom_bar.add_static(name, text)
        self._invalidate_session_cache

    def get_toggle_state(self, key: str) -> bool | None:
        assert isinstance(self.bottom_bar, BottomBar), "Bottom bar must be an instance of BottomBar."
        if key.upper() in self.bottom_bar._states:
            """Returns the state of a toggle."""
            return self.bottom_bar._states[key.upper()][1]
        return None

    def add_help_command(self):
        """Adds a help command to the menu if it doesn't already exist."""
        if not self.help_command:
            self.help_command = self._get_help_command()
            self._invalidate_session_cache()

    def add_history_command(self):
        """Adds a history command to the menu if it doesn't already exist."""
        if not self.history_command:
            self.history_command = self._get_history_command()
            self._invalidate_session_cache()

    def _get_bottom_bar(self) -> Callable[[], Any] | str | None:
        """Returns the bottom bar for the menu."""
        if isinstance(self.bottom_bar, BottomBar) and self.bottom_bar._items:
            return self.bottom_bar.render
        elif callable(self.bottom_bar):
            return self.bottom_bar
        elif isinstance(self.bottom_bar, str):
            return self.bottom_bar
        return None

    @cached_property
    def session(self) -> PromptSession:
        """Returns the prompt session for the menu."""
        return PromptSession(
            message=self.prompt,
            multiline=False,
            completer=self._get_completer(),
            reserve_space_for_menu=1,
            validator=self._get_validator(),
            bottom_toolbar=self._get_bottom_bar(),
            key_bindings=self.key_bindings,
        )

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

        logger.debug(f"Menu-level before hooks: {hook_names(self.hooks._hooks[HookType.BEFORE])}")
        logger.debug(f"Menu-level success hooks: {hook_names(self.hooks._hooks[HookType.ON_SUCCESS])}")
        logger.debug(f"Menu-level error hooks: {hook_names(self.hooks._hooks[HookType.ON_ERROR])}")
        logger.debug(f"Menu-level after hooks: {hook_names(self.hooks._hooks[HookType.AFTER])}")
        logger.debug(f"Menu-level on_teardown hooks: {hook_names(self.hooks._hooks[HookType.ON_TEARDOWN])}")

        for key, command in self.commands.items():
            logger.debug(f"[Command '{key}'] before: {hook_names(command.hooks._hooks[HookType.BEFORE])}")
            logger.debug(f"[Command '{key}'] success: {hook_names(command.hooks._hooks[HookType.ON_SUCCESS])}")
            logger.debug(f"[Command '{key}'] error: {hook_names(command.hooks._hooks[HookType.ON_ERROR])}")
            logger.debug(f"[Command '{key}'] after: {hook_names(command.hooks._hooks[HookType.AFTER])}")
            logger.debug(f"[Command '{key}'] on_teardown: {hook_names(command.hooks._hooks[HookType.ON_TEARDOWN])}")

    def _validate_command_key(self, key: str) -> None:
        """Validates the command key to ensure it is unique."""
        key = key.upper()
        toggles = self.bottom_bar.toggles if isinstance(self.bottom_bar, BottomBar) else []
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
            raise CommandAlreadyExistsError(f"Command key '{key}' conflicts with existing {', '.join(collisions)}.")

    def update_exit_command(
        self,
        key: str = "0",
        description: str = "Exit",
        action: Callable[[], Any] = lambda: None,
        color: str = OneColors.DARK_RED,
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
            action=action,
            color=color,
            confirm=confirm,
            confirm_message=confirm_message,
        )
        self._invalidate_session_cache()

    def add_submenu(self, key: str, description: str, submenu: "Falyx", color: str = OneColors.CYAN) -> None:
        """Adds a submenu to the menu."""
        if not isinstance(submenu, Falyx):
            raise NotAFalyxError("submenu must be an instance of Falyx.")
        self._validate_command_key(key)
        self.add_command(key, description, submenu.menu, color=color)
        self._invalidate_session_cache()

    def add_commands(self, commands: list[dict]) -> None:
        """Adds multiple commands to the menu."""
        for command in commands:
            self.add_command(**command)

    def add_command(
        self,
        key: str,
        description: str,
        action: BaseAction | Callable[[], Any],
        aliases: list[str] | None = None,
        args: tuple = (),
        kwargs: dict[str, Any] = {},
        help_text: str = "",
        color: str = OneColors.WHITE,
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
        after_hooks: list[Callable] | None = None,
        error_hooks: list[Callable] | None = None,
        teardown_hooks: list[Callable] | None = None,
        tags: list[str] | None = None,
        logging_hooks: bool = False,
        retry: bool = False,
        retry_all: bool = False,
        retry_policy: RetryPolicy | None = None,
    ) -> Command:
        """Adds an command to the menu, preventing duplicates."""
        self._validate_command_key(key)
        command = Command(
            key=key,
            description=description,
            aliases=aliases if aliases else [],
            help_text=help_text,
            action=action,
            args=args,
            kwargs=kwargs,
            color=color,
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
        self._invalidate_session_cache()
        return command

    def get_bottom_row(self) -> list[str]:
        """Returns the bottom row of the table for displaying additional commands."""
        bottom_row = []
        if self.history_command:
            bottom_row.append(f"[{self.history_command.key}] [{self.history_command.color}]{self.history_command.description}")
        if self.help_command:
            bottom_row.append(f"[{self.help_command.key}] [{self.help_command.color}]{self.help_command.description}")
        bottom_row.append(f"[{self.exit_command.key}] [{self.exit_command.color}]{self.exit_command.description}")
        return bottom_row

    def build_default_table(self) -> Table:
        """Build the standard table layout. Developers can subclass or call this in custom tables."""
        table = Table(title=self.title, show_header=False, box=box.SIMPLE, expand=True)
        for chunk in chunks(self.commands.items(), self.columns):
            row = []
            for key, command in chunk:
                row.append(f"[{key}] [{command.color}]{command.description}")
            table.add_row(*row)
        bottom_row = self.get_bottom_row()
        table.add_row(*bottom_row)
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

    def get_command(self, choice: str, from_validate=False) -> Command | None:
        """Returns the selected command based on user input. Supports keys, aliases, and abbreviations."""
        choice = choice.upper()
        name_map = self._name_map

        if choice in name_map:
            return name_map[choice]

        prefix_matches = [cmd for key, cmd in name_map.items() if key.startswith(choice)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]

        fuzzy_matches = get_close_matches(choice, list(name_map.keys()), n=3, cutoff=0.7)
        if fuzzy_matches:
            if not from_validate:
                self.console.print(f"[{OneColors.LIGHT_YELLOW}]⚠️ Unknown command '{choice}'. Did you mean:[/] ")
            for match in fuzzy_matches:
                cmd = name_map[match]
                self.console.print(f"  • [bold]{match}[/] → {cmd.description}")
        else:
            if not from_validate:
                self.console.print(f"[{OneColors.LIGHT_YELLOW}]⚠️ Unknown command '{choice}'[/]")
        return None

    async def _should_run_action(self, selected_command: Command) -> bool:
        if self._never_confirm:
            return True

        if self.cli_args and getattr(self.cli_args, "skip_confirm", False):
            return True

        if (self._always_confirm or
            selected_command.confirm or
            self.cli_args and getattr(self.cli_args, "force_confirm", False)
        ):
            if selected_command.preview_before_confirm:
                await selected_command.preview()
            confirm_answer = await async_confirm(selected_command.confirmation_prompt)

            if confirm_answer:
                logger.info(f"[{OneColors.LIGHT_YELLOW}][{selected_command.description}]🔐 confirmed.")
            else:
                logger.info(f"[{OneColors.DARK_RED}][{selected_command.description}]❌ cancelled.")
            return confirm_answer
        return True

    def _create_context(self, selected_command: Command) -> ExecutionContext:
        """Creates a context dictionary for the selected command."""
        return ExecutionContext(
            name=selected_command.description,
            args=tuple(),
            kwargs={},
            action=selected_command,
        )

    async def _run_action_with_spinner(self, command: Command) -> Any:
        """Runs the action of the selected command with a spinner."""
        with self.console.status(
            command.spinner_message,
            spinner=command.spinner_type,
            spinner_style=command.spinner_style,
            **command.spinner_kwargs,
        ):
            return await command()

    async def _handle_action_error(self, selected_command: Command, error: Exception) -> bool:
        """Handles errors that occur during the action of the selected command."""
        logger.exception(f"Error executing '{selected_command.description}': {error}")
        self.console.print(f"[{OneColors.DARK_RED}]An error occurred while executing "
                           f"{selected_command.description}:[/] {error}")
        if self.confirm_on_error and not self._never_confirm:
            return await async_confirm("An error occurred. Do you wish to continue?")
        if self._never_confirm:
            return True
        return False 

    async def process_command(self) -> bool:
        """Processes the action of the selected command."""
        choice = await self.session.prompt_async()
        selected_command = self.get_command(choice)
        if not selected_command:
            logger.info(f"[{OneColors.LIGHT_YELLOW}] Invalid command '{choice}'.")
            return True
        self.last_run_command = selected_command

        if selected_command == self.exit_command:
            logger.info(f"🔙 Back selected: exiting {self.get_title()}")
            return False

        if not await self._should_run_action(selected_command):
            logger.info(f"[{OneColors.DARK_RED}] {selected_command.description} cancelled.")
            return True

        context = self._create_context(selected_command)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            if selected_command.spinner:
                result = await self._run_action_with_spinner(selected_command)
            else:
                result = await selected_command()
            context.result = result
            await self.hooks.trigger(HookType.ON_SUCCESS, context)
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            if not context.exception:
                logger.info(f"✅ Recovery hook handled error for '{selected_command.description}'")
                context.result = result
            else:
                return await self._handle_action_error(selected_command, error)
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)
        return True

    async def headless(self, command_key: str, return_context: bool = False) -> Any:
        """Runs the action of the selected command without displaying the menu."""
        self.debug_hooks()
        selected_command = self.get_command(command_key)
        self.last_run_command = selected_command

        if not selected_command:
            logger.info("[Headless] Back command selected. Exiting menu.")
            return

        logger.info(f"[Headless] 🚀 Running: '{selected_command.description}'")

        if not await self._should_run_action(selected_command):
            raise FalyxError(f"[Headless] '{selected_command.description}' cancelled by confirmation.")

        context = self._create_context(selected_command)
        context.start_timer()
        try:
            await self.hooks.trigger(HookType.BEFORE, context)

            if selected_command.spinner:
                result = await self._run_action_with_spinner(selected_command)
            else:
                result = await selected_command()
            context.result = result

            await self.hooks.trigger(HookType.ON_SUCCESS, context)
            logger.info(f"[Headless] ✅ '{selected_command.description}' complete.")
        except (KeyboardInterrupt, EOFError):
            raise FalyxError(f"[Headless] ⚠️ '{selected_command.description}' interrupted by user.")
        except Exception as error:
            context.exception = error
            await self.hooks.trigger(HookType.ON_ERROR, context)
            if not context.exception:
                logger.info(f"[Headless] ✅ Recovery hook handled error for '{selected_command.description}'")
                return True
            raise FalyxError(f"[Headless] ❌ '{selected_command.description}' failed.") from error
        finally:
            context.stop_timer()
            await self.hooks.trigger(HookType.AFTER, context)
            await self.hooks.trigger(HookType.ON_TEARDOWN, context)

        return context if return_context else context.result

    def _set_retry_policy(self, selected_command: Command) -> None:
        """Sets the retry policy for the command based on CLI arguments."""
        assert isinstance(self.cli_args, Namespace), "CLI arguments must be provided."
        if self.cli_args.retries or self.cli_args.retry_delay or self.cli_args.retry_backoff:
            selected_command.retry_policy.enabled = True
            if self.cli_args.retries:
                selected_command.retry_policy.max_retries = self.cli_args.retries
            if self.cli_args.retry_delay:
                selected_command.retry_policy.delay = self.cli_args.retry_delay
            if self.cli_args.retry_backoff:
                selected_command.retry_policy.backoff = self.cli_args.retry_backoff
            selected_command.update_retry_policy(selected_command.retry_policy)

    def get_arg_parser(self) -> ArgumentParser:
        """Returns the argument parser for the CLI."""
        parser = ArgumentParser(prog="falyx", description="Falyx CLI - Run structured async command workflows.")
        parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging for Falyx.")
        parser.add_argument("--debug-hooks", action="store_true", help="Enable default lifecycle debug logging")
        parser.add_argument("--version", action="store_true", help="Show Falyx version")
        subparsers = parser.add_subparsers(dest="command")

        run_parser = subparsers.add_parser("run", help="Run a specific command")
        run_parser.add_argument("name", help="Key, alias, or description of the command")
        run_parser.add_argument("--retries", type=int, help="Number of retries on failure", default=0)
        run_parser.add_argument("--retry-delay", type=float, help="Initial delay between retries in (seconds)", default=0)
        run_parser.add_argument("--retry-backoff", type=float, help="Backoff factor for retries", default=0)
        run_group = run_parser.add_mutually_exclusive_group(required=False)
        run_group.add_argument("-c", "--confirm", dest="force_confirm", action="store_true", help="Force confirmation prompts")
        run_group.add_argument("-s", "--skip-confirm", dest="skip_confirm", action="store_true", help="Skip confirmation prompts")

        run_all_parser = subparsers.add_parser("run-all", help="Run all commands with a given tag")
        run_all_parser.add_argument("-t", "--tag", required=True, help="Tag to match")
        run_all_parser.add_argument("--retries", type=int, help="Number of retries on failure", default=0)
        run_all_parser.add_argument("--retry-delay", type=float, help="Initial delay between retries in (seconds)", default=0)
        run_all_parser.add_argument("--retry-backoff", type=float, help="Backoff factor for retries", default=0)
        run_all_group = run_all_parser.add_mutually_exclusive_group(required=False)
        run_all_group.add_argument("-c", "--confirm", dest="force_confirm", action="store_true", help="Force confirmation prompts")
        run_all_group.add_argument("-s", "--skip-confirm", dest="skip_confirm", action="store_true", help="Skip confirmation prompts")

        preview_parser = subparsers.add_parser("preview", help="Preview a command without running it")
        preview_parser.add_argument("name", help="Key, alias, or description of the command")

        subparsers.add_parser("list", help="List all available commands with tags")

        subparsers.add_parser("version", help="Show the Falyx version")

        return parser

    async def menu(self) -> None:
        """Runs the menu and handles user input."""
        logger.info(f"Running menu: {self.get_title()}")
        self.debug_hooks()
        if self.welcome_message:
            self.console.print(self.welcome_message)
        while True:
            self.console.print(self.table)
            try:
                task = asyncio.create_task(self.process_command())
                should_continue = await task
                if not should_continue:
                    break
            except (EOFError, KeyboardInterrupt):
                logger.info(f"[{OneColors.DARK_RED}]EOF or KeyboardInterrupt. Exiting menu.")
                break
        logger.info(f"Exiting menu: {self.get_title()}")
        if self.exit_message:
            self.console.print(self.exit_message)

    async def run(self, parser: ArgumentParser | None = None) -> None:
        """Run Falyx CLI with structured subcommands."""
        parser = parser or self.get_arg_parser()
        self.cli_args = parser.parse_args()

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
            command = self.get_command(self.cli_args.name)
            if not command:
                self.console.print(f"[{OneColors.DARK_RED}]❌ Command '{self.cli_args.name}' not found.[/]")
                sys.exit(1)
            self.console.print(f"Preview of command '{command.key}': {command.description}")
            await command.preview()
            sys.exit(0)

        if self.cli_args.command == "run":
            command = self.get_command(self.cli_args.name)
            if not command:
                self.console.print(f"[{OneColors.DARK_RED}]❌ Command '{self.cli_args.name}' not found.[/]")
                sys.exit(1)
            self._set_retry_policy(command)
            try:
                result = await self.headless(self.cli_args.name)
            except FalyxError as error:
                self.console.print(f"[{OneColors.DARK_RED}]❌ Error: {error}[/]")
                sys.exit(1)
            self.console.print(f"[{OneColors.GREEN}]✅ Result:[/] {result}")
            sys.exit(0)

        if self.cli_args.command == "run-all":
            matching = [
                cmd for cmd in self.commands.values()
                if self.cli_args.tag.lower() in (tag.lower() for tag in cmd.tags)
            ]
            if not matching:
                self.console.print(f"[{OneColors.LIGHT_YELLOW}]⚠️ No commands found with tag: '{self.cli_args.tag}'[/]")
                sys.exit(1)

            self.console.print(f"[bold cyan]🚀 Running all commands with tag:[/] {self.cli_args.tag}")
            for cmd in matching:
                self._set_retry_policy(cmd)
                await self.headless(cmd.key)
            sys.exit(0)

        await self.menu()
