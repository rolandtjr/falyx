# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""CommandArgumentParser implementation for the Falyx CLI framework.

This module provides a structured, extensible argument parsing system designed
specifically for Falyx commands. It replaces traditional argparse usage with a
parser that is deeply integrated with Falyx's execution model, including support
for Actions, execution options, and interactive completion.

The parser is designed to:
- Define command arguments declaratively via `add_argument`
- Support both positional and keyword-style flags
- Perform type coercion and validation
- Separate execution-level options (e.g. retries, confirmation) from command inputs
- Integrate with Falyx lifecycle and Action-based execution
- Provide rich help rendering and interactive suggestions

Key Features:
- Positional and flagged argument support
- Type coercion via configurable `type` handlers
- Enum-driven behavior via `ArgumentAction`
- Lazy and eager resolution using BaseAction resolvers
- Execution option support (e.g. retries, summary, confirm flags)
- Mutually exclusive and grouped argument definitions
- POSIX-style short flag bundling (e.g. `-abc`)
- Interactive suggestions via `suggest_next`
- Rich-based help and TLDR rendering

Core Parsing APIs:
- `parse_args(...)`:
    Parse arguments into a resolved dictionary of values
- `parse_args_split(...)`:
    Split parsed results into `(args, kwargs, execution_args)` for execution
- `add_argument(...)`:
    Register argument definitions declaratively
- `suggest_next(...)`:
    Provide completion suggestions for interactive input

Design Principles:
- Minimal surface area compared to argparse
- Strong integration with Falyx execution model
- Predictable and explicit parsing behavior
- Separation of parsing, execution, and runtime configuration

This parser is intended for use exclusively within Falyx and is not a
general-purpose argparse replacement.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Generator, Iterable, Sequence

from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.panel import Panel

from falyx.action.base_action import BaseAction
from falyx.console import console
from falyx.exceptions import CommandArgumentError, NotAFalyxError
from falyx.execution_option import ExecutionOption
from falyx.mode import FalyxMode
from falyx.options_manager import OptionsManager
from falyx.parser.argument import Argument
from falyx.parser.argument_action import ArgumentAction
from falyx.parser.group import ArgumentGroup, MutuallyExclusiveGroup
from falyx.parser.parser_types import ArgumentState, TLDRExample, false_none, true_none
from falyx.parser.utils import coerce_value
from falyx.signals import HelpSignal


class _GroupBuilder:
    """Helper for assigning arguments to a named group or mutex group.

    This lightweight wrapper preserves the normal `add_argument()` API while
    injecting `group` or `mutex_group` metadata into each registered argument.

    Args:
        parser (CommandArgumentParser): Parser that owns the group definitions.
        group_name (str | None): Name of the argument group to assign.
        mutex_name (str | None): Name of the mutually exclusive group to assign.
    """

    def __init__(
        self,
        parser: CommandArgumentParser,
        *,
        group_name: str | None = None,
        mutex_name: str | None = None,
    ) -> None:
        self.parser = parser
        self.group_name = group_name
        self.mutex_name = mutex_name

    def add_argument(self, *flags, **kwargs) -> None:
        self.parser.add_argument(
            *flags,
            group=self.group_name,
            mutex_group=self.mutex_name,
            **kwargs,
        )


class CommandArgumentParser:
    """
    Custom argument parser for Falyx Commands.
    It is used to create a command-line interface for Falyx
    commands, allowing users to specify options and arguments
    when executing commands.
    It is not intended to be a full-featured replacement for
    argparse, but rather a lightweight alternative for specific use
    cases within the Falyx framework.

    Features:
    - Customizable argument parsing.
    - Type coercion for arguments.
    - Support for positional and keyword arguments.
    - Support for default values.
    - Support for boolean flags.
    - Support for optional boolean flags.
    - Exception handling for invalid arguments.
    - Render Help using Rich library.
    """

    RESERVED_DESTS = frozenset({"help", "tldr"})

    def __init__(
        self,
        command_key: str = "",
        command_description: str = "",
        command_style: str = "bold",
        help_text: str = "",
        help_epilog: str = "",
        aliases: list[str] | None = None,
        tldr_examples: list[tuple[str, str]] | None = None,
        program: str | None = None,
        options_manager: OptionsManager | None = None,
        _is_help_command: bool = False,
    ) -> None:
        """Initialize the CommandArgumentParser."""
        self.console: Console = console
        self.command_key: str = command_key
        self.command_description: str = command_description
        self.command_style: str = command_style
        self.help_text: str = help_text
        self.help_epilog: str = help_epilog
        self.aliases: list[str] = aliases or []
        self.program: str | None = program
        self._arguments: list[Argument] = []
        self._positional: dict[str, Argument] = {}
        self._keyword: dict[str, Argument] = {}
        self._keyword_list: list[Argument] = []
        self._flag_map: dict[str, Argument] = {}
        self._dest_set: set[str] = set()
        self._execution_dests: set[str] = set()
        self._add_help()
        self._last_positional_states: dict[str, ArgumentState] = {}
        self._last_keyword_states: dict[str, ArgumentState] = {}
        self._argument_groups: dict[str, ArgumentGroup] = {}
        self._mutex_groups: dict[str, MutuallyExclusiveGroup] = {}
        self._arg_group_by_dest: dict[str, str] = {}
        self._mutex_group_by_dest: dict[str, str] = {}
        self._tldr_examples: list[TLDRExample] = []
        self._is_help_command: bool = _is_help_command
        if tldr_examples:
            self.add_tldr_examples(tldr_examples)
        self.options_manager: OptionsManager = options_manager or OptionsManager()

    def set_options_manager(self, options_manager: OptionsManager) -> None:
        """Set the options manager for the parser."""
        if not isinstance(options_manager, OptionsManager):
            raise NotAFalyxError("options_manager must be an instance of OptionsManager")
        self.options_manager = options_manager

    def enable_execution_options(
        self,
        execution_options: frozenset[ExecutionOption],
    ) -> None:
        """Enable support for execution options like retries, summary, etc."""
        if ExecutionOption.SUMMARY in execution_options:
            self.add_argument(
                "--summary",
                action=ArgumentAction.STORE_TRUE,
                help="Print an execution summary after command completes",
            )
            self._register_execution_dest("summary")

        if ExecutionOption.RETRY in execution_options:
            self.add_argument(
                "--retries",
                type=int,
                help="Number of retries on failure",
                default=0,
            )
            self._register_execution_dest("retries")
            self.add_argument(
                "--retry-delay",
                type=float,
                default=0.0,
                help="Initial delay between retries in seconds",
            )
            self._register_execution_dest("retry_delay")
            self.add_argument(
                "--retry-backoff",
                type=float,
                default=0.0,
                help="Backoff multiplier for retries (e.g. 2.0 doubles the delay each retry)",
            )
            self._register_execution_dest("retry_backoff")

        if ExecutionOption.CONFIRM in execution_options:
            self.add_argument(
                "--confirm",
                dest="force_confirm",
                action=ArgumentAction.STORE_TRUE,
                help="Force confirmation prompts",
            )
            self._register_execution_dest("force_confirm")
            self.add_argument(
                "--skip-confirm",
                action=ArgumentAction.STORE_TRUE,
                help="Skip confirmation prompts",
            )
            self._register_execution_dest("skip_confirm")

    def _register_execution_dest(self, dest: str) -> None:
        """Register a destination as an execution argument."""
        if dest in self._execution_dests:
            raise CommandArgumentError(
                f"Destination '{dest}' is already registered as an execution argument"
            )
        self._execution_dests.add(dest)

    def _is_execution_dest(self, dest: str) -> bool:
        """Check if a destination is registered as an execution argument."""
        return dest in self._execution_dests

    def _add_help(self):
        """Add help argument to the parser."""
        help = Argument(
            flags=("--help", "-h"),
            action=ArgumentAction.HELP,
            help="Show this help message.",
            dest="help",
        )
        self._register_argument(help)

    def add_tldr_examples(self, examples: list[tuple[str, str]]) -> None:
        """
        Add TLDR examples to the parser.

        Args:
            examples (list[tuple[str, str]]): List of (usage, description) tuples.
        """
        if not all(
            isinstance(example, tuple) and len(example) == 2 for example in examples
        ):
            raise CommandArgumentError(
                "TLDR examples must be a list of (usage, description) tuples"
            )

        for usage, description in examples:
            self._tldr_examples.append(TLDRExample(usage=usage, description=description))

        if "tldr" not in self._dest_set:
            tldr = Argument(
                ("--tldr", "-T"),
                action=ArgumentAction.TLDR,
                help="Show quick usage examples.",
                dest="tldr",
            )
            self._register_argument(tldr)

    def add_argument_group(
        self,
        name: str,
        description: str = "",
    ) -> _GroupBuilder:
        if name in self._argument_groups:
            raise CommandArgumentError(f"Argument group '{name}' already exists")
        self._argument_groups[name] = ArgumentGroup(name=name, description=description)
        return _GroupBuilder(self, group_name=name)

    def add_mutually_exclusive_group(
        self,
        name: str,
        *,
        required: bool = False,
        description: str = "",
    ) -> _GroupBuilder:
        if name in self._mutex_groups:
            raise CommandArgumentError(f"Mutex group '{name}' already exists")
        self._mutex_groups[name] = MutuallyExclusiveGroup(
            name=name,
            required=required,
            description=description,
        )
        return _GroupBuilder(self, mutex_name=name)

    def _is_positional(self, flags: tuple[str, ...]) -> bool:
        """Check if the flags are positional."""
        positional = False
        if any(not flag.startswith("-") for flag in flags):
            positional = True

        if positional and len(flags) > 1:
            raise CommandArgumentError("Positional arguments cannot have multiple flags")
        return positional

    def _validate_groups(
        self,
        group: str | None,
        mutex_group: str | None,
        positional: bool = False,
        required: bool = False,
    ) -> None:
        """Validate that the specified groups exist and are compatible."""
        if group is not None:
            if group not in self._argument_groups:
                raise CommandArgumentError(f"Argument group '{group}' does not exist")

        if mutex_group is not None:
            if mutex_group not in self._mutex_groups:
                raise CommandArgumentError(
                    f"Mutually exclusive group '{mutex_group}' does not exist"
                )
        if positional and mutex_group is not None:
            raise CommandArgumentError(
                "Positional arguments cannot belong to a mutually exclusive group"
            )

        if required and mutex_group is not None:
            raise CommandArgumentError(
                "Arguments inside a mutually exclusive group should not be individually required; "
                "make the group required instead."
            )

    def _get_dest_from_flags(self, flags: tuple[str, ...], dest: str | None) -> str:
        """Convert flags to a destination name."""
        if dest:
            if not dest.replace("_", "").isalnum():
                raise CommandArgumentError(
                    "dest must be a valid identifier (letters, digits, and underscores only)"
                )
            if dest[0].isdigit():
                raise CommandArgumentError("dest must not start with a digit")
            return dest
        dest = None
        for flag in flags:
            if flag.startswith("--"):
                dest = flag.lstrip("-").replace("-", "_").lower()
                break
            elif flag.startswith("-"):
                dest = flag.lstrip("-").replace("-", "_").lower()
            else:
                dest = flag.replace("-", "_").lower()
        assert dest is not None, "dest should not be None"
        if not dest.replace("_", "").isalnum():
            raise CommandArgumentError(
                "dest must be a valid identifier (letters, digits, and underscores only)"
            )
        if dest[0].isdigit():
            raise CommandArgumentError("dest must not start with a digit")
        return dest

    def _determine_required(
        self,
        required: bool,
        positional: bool,
        nargs: int | str | None,
        action: ArgumentAction,
    ) -> bool:
        """Determine if the argument is required."""
        if required:
            if action in (
                ArgumentAction.STORE_TRUE,
                ArgumentAction.STORE_FALSE,
                ArgumentAction.STORE_BOOL_OPTIONAL,
                ArgumentAction.HELP,
                ArgumentAction.TLDR,
            ):
                raise CommandArgumentError(
                    f"Argument with action {action} cannot be required"
                )
            return True
        if positional:
            assert (
                nargs is None
                or isinstance(nargs, int)
                or isinstance(nargs, str)
                and nargs in ("+", "*", "?")
            ), f"Invalid nargs value: {nargs}"
            if isinstance(nargs, int):
                return nargs > 0
            elif isinstance(nargs, str):
                if nargs in ("+"):
                    return True
                elif nargs in ("*", "?"):
                    return False
            else:
                return True

        return required

    def _validate_nargs(
        self, nargs: int | str | None, action: ArgumentAction
    ) -> int | str | None:
        """Validate the nargs value for the argument."""
        if action in (
            ArgumentAction.STORE_FALSE,
            ArgumentAction.STORE_TRUE,
            ArgumentAction.COUNT,
            ArgumentAction.HELP,
            ArgumentAction.TLDR,
            ArgumentAction.STORE_BOOL_OPTIONAL,
        ):
            if nargs is not None:
                raise CommandArgumentError(
                    f"nargs cannot be specified for {action} actions"
                )
            return None
        if nargs is None:
            return None
        allowed_nargs = ("?", "*", "+")
        if isinstance(nargs, int):
            if nargs <= 0:
                raise CommandArgumentError("nargs must be a positive integer")
        elif isinstance(nargs, str):
            if nargs not in allowed_nargs:
                raise CommandArgumentError(f"Invalid nargs value: {nargs}")
        else:
            raise CommandArgumentError(f"nargs must be an int or one of {allowed_nargs}")
        return nargs

    def _normalize_choices(
        self, choices: Iterable | None, expected_type: Any, action: ArgumentAction
    ) -> list[Any]:
        """Normalize and validate choices for the argument."""
        if choices is not None:
            if action in (
                ArgumentAction.STORE_TRUE,
                ArgumentAction.STORE_FALSE,
                ArgumentAction.STORE_BOOL_OPTIONAL,
            ):
                raise CommandArgumentError(
                    f"choices cannot be specified for {action} actions"
                )
            if isinstance(choices, dict):
                raise CommandArgumentError("choices cannot be a dict")
            try:
                choices = list(choices)
            except TypeError as error:
                raise CommandArgumentError(
                    "choices must be iterable (like list, tuple, or set)"
                ) from error
        else:
            choices = []
        for choice in choices:
            try:
                coerce_value(choice, expected_type)
            except Exception as error:
                raise CommandArgumentError(
                    f"Invalid choice {choice!r}: not coercible to {expected_type.__name__} error: {error}"
                ) from error
        return choices

    def _validate_default_type(
        self, default: Any, expected_type: type, dest: str
    ) -> None:
        """Validate the default value type."""
        if default is not None:
            try:
                coerce_value(default, expected_type)
            except Exception as error:
                raise CommandArgumentError(
                    f"Default value {default!r} for '{dest}' cannot be coerced to {expected_type.__name__} error: {error}"
                ) from error

    def _validate_default_list_type(
        self, default: list[Any], expected_type: type, dest: str
    ) -> None:
        """Validate the default value type for a list."""
        if isinstance(default, list):
            for item in default:
                try:
                    coerce_value(item, expected_type)
                except Exception as error:
                    raise CommandArgumentError(
                        f"Default list value {default!r} for '{dest}' cannot be coerced to {expected_type.__name__} error: {error}"
                    ) from error

    def _validate_resolver(
        self, action: ArgumentAction, resolver: BaseAction | None
    ) -> BaseAction | None:
        """Validate the action object."""
        if action != ArgumentAction.ACTION and resolver is None:
            return None
        elif action == ArgumentAction.ACTION and resolver is None:
            raise CommandArgumentError("resolver must be provided for ACTION action")
        elif action != ArgumentAction.ACTION and resolver is not None:
            raise CommandArgumentError(
                f"resolver should not be provided for action {action}"
            )

        if not isinstance(resolver, BaseAction):
            raise CommandArgumentError("resolver must be an instance of BaseAction")
        return resolver

    def _validate_action(
        self, action: ArgumentAction | str, positional: bool
    ) -> ArgumentAction:
        """Validate the action type."""
        if not isinstance(action, ArgumentAction):
            try:
                action = ArgumentAction(action)
            except ValueError as error:
                raise CommandArgumentError(
                    f"Invalid action '{action}' is not a valid ArgumentAction"
                ) from error
        if action in (
            ArgumentAction.STORE_TRUE,
            ArgumentAction.STORE_FALSE,
            ArgumentAction.STORE_BOOL_OPTIONAL,
            ArgumentAction.COUNT,
            ArgumentAction.HELP,
            ArgumentAction.TLDR,
        ):
            if positional:
                raise CommandArgumentError(
                    f"Action '{action}' cannot be used with positional arguments"
                )

        return action

    def _resolve_default(
        self,
        default: Any,
        action: ArgumentAction,
        nargs: str | int | None,
    ) -> Any:
        """Get the default value for the argument."""
        if default is None:
            if action == ArgumentAction.STORE_TRUE:
                return False
            elif action == ArgumentAction.STORE_FALSE:
                return True
            elif action == ArgumentAction.COUNT:
                return 0
            elif action in (ArgumentAction.APPEND, ArgumentAction.EXTEND):
                return []
            elif isinstance(nargs, int):
                return []
            elif nargs in ("+", "*"):
                return []
            else:
                return None
        elif action in (
            ArgumentAction.STORE_TRUE,
            ArgumentAction.STORE_FALSE,
            ArgumentAction.STORE_BOOL_OPTIONAL,
        ):
            raise CommandArgumentError(
                f"Default value cannot be set for action {action}. It is a boolean flag."
            )
        elif action in (ArgumentAction.HELP, ArgumentAction.TLDR, ArgumentAction.COUNT):
            raise CommandArgumentError(
                f"Default value cannot be set for action {action}."
            )

        if action in (ArgumentAction.APPEND, ArgumentAction.EXTEND) and not isinstance(
            default, list
        ):
            raise CommandArgumentError(
                f"Default value for action {action} must be a list, got {type(default).__name__}"
            )
        if isinstance(nargs, int) and nargs == 1:
            if not isinstance(default, list):
                default = [default]
        if isinstance(nargs, int) or nargs in ("*", "+"):
            if not isinstance(default, list):
                raise CommandArgumentError(
                    f"Default value for action {action} with nargs {nargs} must be a list, got {type(default).__name__}"
                )
        return default

    def _validate_flags(self, flags: tuple[str, ...]) -> None:
        """Validate the flags provided for the argument."""
        if not flags:
            raise CommandArgumentError("No flags provided")
        for flag in flags:
            if not isinstance(flag, str):
                raise CommandArgumentError(f"Flag '{flag}' must be a string")
            if flag.startswith("--") and len(flag) < 3:
                raise CommandArgumentError(
                    f"Flag '{flag}' must be at least 3 characters long"
                )
            if flag.startswith("-") and not flag.startswith("--") and len(flag) > 2:
                raise CommandArgumentError(
                    f"Flag '{flag}' must be a single character or start with '--'"
                )

    def _register_store_bool_optional(
        self,
        flags: tuple[str, ...],
        dest: str,
        help: str,
        group: str | None,
        mutex_group: str | None,
    ) -> None:
        """Register a store_bool_optional action with the parser."""
        if len(flags) != 1:
            raise CommandArgumentError(
                "store_bool_optional action can only have a single flag"
            )
        if not flags[0].startswith("--"):
            raise CommandArgumentError(
                "store_bool_optional action must use a long flag (e.g. --flag)"
            )
        base_flag = flags[0]
        negated_flag = f"--no-{base_flag.lstrip('-')}"

        argument = Argument(
            flags=flags,
            dest=dest,
            action=ArgumentAction.STORE_BOOL_OPTIONAL,
            type=true_none,
            default=None,
            help=help,
            group=group,
            mutex_group=mutex_group,
        )

        negated_argument = Argument(
            flags=(negated_flag,),
            dest=dest,
            action=ArgumentAction.STORE_BOOL_OPTIONAL,
            type=false_none,
            default=None,
            help=help,
            group=group,
            mutex_group=mutex_group,
        )

        self._register_argument(argument)
        self._register_argument(negated_argument, bypass_validation=True)

    def _register_argument(
        self, argument: Argument, bypass_validation: bool = False
    ) -> None:
        """Register a new argument with the parser."""
        for flag in argument.flags:
            if flag in self._flag_map and not bypass_validation:
                existing = self._flag_map[flag]
                raise CommandArgumentError(
                    f"Flag '{flag}' is already used by argument '{existing.dest}'"
                )

        for flag in argument.flags:
            self._flag_map[flag] = argument
            if not argument.positional:
                self._keyword[flag] = argument
        self._dest_set.add(argument.dest)
        self._arguments.append(argument)
        if argument.positional:
            self._positional[argument.dest] = argument
        else:
            if argument.action == ArgumentAction.TLDR:
                self._keyword_list.insert(1, argument)
            else:
                self._keyword_list.append(argument)

        if argument.group:
            self._arg_group_by_dest[argument.dest] = argument.group
            self._argument_groups[argument.group].dests.append(argument.dest)

        if argument.mutex_group:
            self._mutex_group_by_dest[argument.dest] = argument.mutex_group
            self._mutex_groups[argument.mutex_group].dests.append(argument.dest)

    def add_argument(
        self,
        *flags,
        action: str | ArgumentAction = "store",
        nargs: int | str | None = None,
        default: Any = None,
        type: Any = str,
        choices: Iterable | None = None,
        required: bool = False,
        help: str = "",
        dest: str | None = None,
        resolver: BaseAction | None = None,
        lazy_resolver: bool = True,
        suggestions: list[str] | None = None,
        group: str | None = None,
        mutex_group: str | None = None,
    ) -> None:
        """
        Define a new argument for the parser.

        Supports positional and flagged arguments, type coercion, default values,
        validation rules, and optional resolution via `BaseAction`.

        Args:
            *flags (str): The flag(s) or name identifying the argument (e.g., "-v", "--verbose").
            action (str | ArgumentAction): The argument action type (default: "store").
            nargs (int | str | None): Number of values the argument consumes.
            default (Any): Default value if the argument is not provided.
            type (type): Type to coerce argument values to.
            choices (Iterable | None): Optional set of allowed values.
            required (bool): Whether this argument is mandatory.
            help (str): Help text for rendering in command help.
            dest (str | None): Custom destination key in result dict.
            resolver (BaseAction | None): If action="action", the BaseAction to call.
            lazy_resolver (bool): If True, resolver defers until action is triggered.
            suggestions (list[str] | None): Optional suggestions for interactive completion.
            group (str | None): Optional argument group name for help organization.
            mutex_group (str | None): Optional mutually exclusive group name.
        """
        expected_type = type
        self._validate_flags(flags)
        positional = self._is_positional(flags)
        dest = self._get_dest_from_flags(flags, dest)
        if dest in self._dest_set:
            raise CommandArgumentError(
                f"Destination '{dest}' is already defined.\n"
                "Merging multiple arguments into the same dest (e.g. positional + flagged) "
                "is not supported. Define a unique 'dest' for each argument."
            )
        if dest in self.RESERVED_DESTS:
            raise CommandArgumentError(
                f"Destination '{dest}' is reserved and cannot be used."
            )

        self._validate_groups(group, mutex_group, positional, required)

        action = self._validate_action(action, positional)
        resolver = self._validate_resolver(action, resolver)

        nargs = self._validate_nargs(nargs, action)
        default = self._resolve_default(default, action, nargs)
        if (
            action in (ArgumentAction.STORE, ArgumentAction.APPEND, ArgumentAction.EXTEND)
            and default is not None
        ):
            if isinstance(default, list):
                self._validate_default_list_type(default, expected_type, dest)
            else:
                self._validate_default_type(default, expected_type, dest)
        choices = self._normalize_choices(choices, expected_type, action)
        if default is not None and choices:
            if isinstance(default, list):
                if not all(choice in choices for choice in default):
                    raise CommandArgumentError(
                        f"Default list value {default!r} for '{dest}' must be a subset of choices: {choices}"
                    )
            elif default not in choices:
                # If default is not in choices, raise an error
                raise CommandArgumentError(
                    f"Default value '{default}' not in allowed choices: {choices}"
                )
        required = self._determine_required(required, positional, nargs, action)
        if not isinstance(suggestions, Sequence) and suggestions is not None:
            raise CommandArgumentError(
                f"suggestions must be a list or None, got {type(suggestions)}"
            )
        if not isinstance(lazy_resolver, bool):
            raise CommandArgumentError(
                f"lazy_resolver must be a boolean, got {type(lazy_resolver)}"
            )
        if action == ArgumentAction.STORE_BOOL_OPTIONAL:
            self._register_store_bool_optional(flags, dest, help, group, mutex_group)
        else:
            argument = Argument(
                flags=flags,
                dest=dest,
                action=action,
                type=expected_type,
                default=default,
                choices=choices,
                required=required,
                help=help,
                nargs=nargs,
                positional=positional,
                resolver=resolver,
                lazy_resolver=lazy_resolver,
                suggestions=suggestions,
                group=group,
                mutex_group=mutex_group,
            )
            self._register_argument(argument)

    def get_argument(self, dest: str) -> Argument | None:
        """
        Return the Argument object for a given destination name.

        Args:
            dest (str): Destination key of the argument.

        Returns:
            Argument or None: Matching Argument instance, if defined.
        """
        return next(
            (argument for argument in self._arguments if argument.dest == dest), None
        )

    def to_definition_list(self) -> list[dict[str, Any]]:
        """
        Convert argument metadata into a serializable list of dicts.

        Returns:
            List of definitions for use in config introspection, documentation, or export.
        """
        defs = []
        for arg in self._arguments:
            defs.append(
                {
                    "flags": arg.flags,
                    "dest": arg.dest,
                    "action": arg.action,
                    "type": arg.type,
                    "choices": arg.choices,
                    "required": arg.required,
                    "nargs": arg.nargs,
                    "positional": arg.positional,
                    "default": arg.default,
                    "help": arg.help,
                    "group": arg.group,
                    "mutex_group": arg.mutex_group,
                }
            )
        return defs

    def _check_if_in_choices(
        self,
        spec: Argument,
        result: dict[str, Any],
        arg_states: dict[str, ArgumentState],
    ) -> None:
        """Check if the value is in the choices for the argument."""
        if not spec.choices:
            return None
        value_check = result.get(spec.dest)
        if isinstance(value_check, list):
            if all(value in spec.choices for value in value_check):
                return None
        if value_check in spec.choices:
            return None
        arg_states[spec.dest].reset()
        arg_states[spec.dest].has_invalid_choice = True
        raise CommandArgumentError(
            f"Invalid value for '{spec.dest}': must be one of {{{', '.join(spec.choices)}}}"
        )

    def _raise_remaining_args_error(
        self, token: str, arg_states: dict[str, ArgumentState]
    ) -> None:
        """Raise an error for unrecognized options with suggestions."""
        consumed_dests = [
            state.arg.dest for state in arg_states.values() if state.consumed
        ]
        remaining_flags = [
            flag
            for flag, arg in self._keyword.items()
            if arg.dest not in consumed_dests and flag.startswith(token)
        ]

        if remaining_flags:
            raise CommandArgumentError(
                f"Unrecognized option '{token}'. Did you mean one of: {', '.join(remaining_flags)}?"
            )
        else:
            raise CommandArgumentError(
                f"Unrecognized option '{token}'. Use --help to see available options."
            )

    def _consume_nargs(
        self, args: list[str], index: int, spec: Argument
    ) -> tuple[list[str], int]:
        """Consume the specified number of arguments based on nargs."""
        assert (
            spec.nargs is None
            or isinstance(spec.nargs, int)
            or isinstance(spec.nargs, str)
            and spec.nargs in ("+", "*", "?")
        ), f"Invalid nargs value: {spec.nargs}"
        values = []
        if isinstance(spec.nargs, int):
            if index + spec.nargs > len(args):
                raise CommandArgumentError(
                    f"Expected {spec.nargs} value(s) for '{spec.dest}' but got {len(args) - index}"
                )
            values = args[index : index + spec.nargs]
            return values, index + spec.nargs
        elif spec.nargs == "+":
            if index >= len(args):
                raise CommandArgumentError(
                    f"Expected at least one value for '{spec.dest}'"
                )
            while index < len(args) and args[index] not in self._keyword:
                values.append(args[index])
                index += 1
            assert values, "Expected at least one value for '+' nargs: shouldn't happen"
            return values, index
        elif spec.nargs == "*":
            while index < len(args) and args[index] not in self._keyword:
                values.append(args[index])
                index += 1
            return values, index
        elif spec.nargs == "?":
            if index < len(args) and args[index] not in self._keyword:
                return [args[index]], index + 1
            return [], index
        elif spec.nargs is None:
            if index < len(args) and args[index] not in self._keyword:
                return [args[index]], index + 1
            return [], index
        assert False, "Invalid nargs value: shouldn't happen"

    async def _consume_all_positional_args(
        self,
        args: list[str],
        result: dict[str, Any],
        positional_args: list[Argument],
        consumed_positional_indicies: set[int],
        arg_states: dict[str, ArgumentState],
        from_validate: bool = False,
        base_index: int = 0,
    ) -> int:
        """Consume all positional arguments from the provided args list."""
        remaining_positional_args = [
            (spec_index, spec)
            for spec_index, spec in enumerate(positional_args)
            if spec_index not in consumed_positional_indicies
        ]
        index = 0
        for spec_index, spec in remaining_positional_args:
            # estimate how many args the remaining specs might need
            is_last = spec_index == len(positional_args) - 1
            remaining = len(args) - index
            min_required = 0
            for next_spec in positional_args[spec_index + 1 :]:
                assert (
                    next_spec.nargs is None
                    or isinstance(next_spec.nargs, int)
                    or isinstance(next_spec.nargs, str)
                    and next_spec.nargs in ("+", "*", "?")
                ), f"Invalid nargs value: {spec.nargs}"

                if next_spec.default:
                    continue

                if next_spec.nargs is None:
                    min_required += 1
                elif isinstance(next_spec.nargs, int):
                    min_required += next_spec.nargs
                elif next_spec.nargs == "+":
                    min_required += 1
                elif next_spec.nargs == "?":
                    continue
                elif next_spec.nargs == "*":
                    continue

            slice_args = (
                args[index:]
                if is_last
                else args[index : index + (remaining - min_required)]
            )
            values, new_index = self._consume_nargs(slice_args, 0, spec)
            index += new_index
            try:
                typed = [coerce_value(value, spec.type) for value in values]
            except Exception as error:
                if len(args[index - new_index :]) == 1 and args[
                    index - new_index
                ].startswith("-"):
                    token = args[index - new_index]
                    self._raise_remaining_args_error(token, arg_states)
                else:
                    arg_states[spec.dest].reset()
                    arg_states[spec.dest].has_invalid_choice = True
                    raise CommandArgumentError(
                        f"Invalid value for '{spec.dest}': {error}"
                    ) from error
            if spec.action == ArgumentAction.ACTION:
                assert isinstance(
                    spec.resolver, BaseAction
                ), "resolver should be an instance of BaseAction"
                if spec.nargs == "+" and len(typed) == 0:
                    raise CommandArgumentError(
                        f"Argument '{spec.dest}' requires at least one value"
                    )
                if isinstance(spec.nargs, int) and len(typed) != spec.nargs:
                    raise CommandArgumentError(
                        f"Argument '{spec.dest}' requires exactly {spec.nargs} value(s)"
                    )
                if not spec.lazy_resolver or not from_validate:
                    try:
                        result[spec.dest] = await spec.resolver(*typed)
                    except Exception as error:
                        raise CommandArgumentError(
                            f"[{spec.dest}] Action failed: {error}"
                        ) from error
                self._check_if_in_choices(spec, result, arg_states)
                arg_states[spec.dest].set_consumed(base_index + index)
            elif not typed and spec.default:
                result[spec.dest] = spec.default
            elif spec.action == ArgumentAction.APPEND:
                assert result.get(spec.dest) is not None, "dest should not be None"
                if not typed:
                    self._raise_suggestion_error(spec)
                if spec.nargs is None:
                    result[spec.dest].append(typed[0])
                else:
                    result[spec.dest].append(typed)
            elif spec.action == ArgumentAction.EXTEND:
                assert result.get(spec.dest) is not None, "dest should not be None"
                result[spec.dest].extend(typed)
            elif spec.nargs in (None, 1, "?"):
                result[spec.dest] = typed[0] if len(typed) == 1 else typed
                self._check_if_in_choices(spec, result, arg_states)
                arg_states[spec.dest].set_consumed(base_index + index)
            else:
                self._check_if_in_choices(spec, result, arg_states)
                arg_states[spec.dest].set_consumed(base_index + index)
                result[spec.dest] = typed

            if spec.nargs not in ("*", "+"):
                consumed_positional_indicies.add(spec_index)
        if index < len(args):
            if len(args[index:]) == 1 and args[index].startswith("-"):
                token = args[index]
                self._raise_remaining_args_error(token, arg_states)
            else:
                plural = "s" if len(args[index:]) > 1 else ""
                raise CommandArgumentError(
                    f"Unexpected positional argument{plural}: {', '.join(args[index:])}"
                )

        return index

    def _expand_posix_bundling(
        self, token: str, last_flag_argument: Argument | None
    ) -> list[str] | str:
        """Expand POSIX-style bundled arguments into separate arguments."""
        expanded = []
        if last_flag_argument:
            if last_flag_argument.type is not str and last_flag_argument.action not in (
                ArgumentAction.STORE_TRUE,
                ArgumentAction.STORE_FALSE,
                ArgumentAction.STORE_BOOL_OPTIONAL,
                ArgumentAction.COUNT,
                ArgumentAction.HELP,
                ArgumentAction.TLDR,
            ):
                try:
                    last_flag_argument.type(token)
                    return token
                except (ValueError, TypeError):
                    pass

        if (
            token.startswith("-")
            and not token.startswith("--")
            and len(token) > 2
            and not self._is_valid_dash_token_positional_value(token)
        ):
            # POSIX bundle
            # e.g. -abc -> -a -b -c
            for char in token[1:]:
                flag = f"-{char}"
                arg = self._flag_map.get(flag)
                if not arg:
                    raise CommandArgumentError(f"Unrecognized option: {flag}")
                expanded.append(flag)
        else:
            return token
        return expanded

    def _is_valid_dash_token_positional_value(self, token: str) -> bool:
        """Checks if any remaining positional arguments take valid dash-prefixed values."""
        valid = False
        try:
            for arg in self._positional.values():
                if arg.type is not str:
                    arg.type(token)
                    valid = True
                    break
        except (ValueError, TypeError):
            valid = False
        return valid

    def _raise_suggestion_error(self, spec: Argument) -> None:
        """Raise an error with suggestions for the argument."""
        help_text = f"help: {spec.help}" if spec.help else ""
        choices = []
        if spec.default:
            choices.append(f"default={spec.default}")
        if spec.choices:
            choices.append(f"choices={spec.choices}")
        if choices:
            choices.append(help_text)
            choices_text = ", ".join(choices)
            raise CommandArgumentError(
                f"Argument '{spec.dest}' requires a value. {choices_text}"
            )
        elif spec.nargs is None:
            try:
                raise CommandArgumentError(
                    f"Enter a {spec.type.__name__} value for '{spec.dest}'. {help_text}"
                )
            except AttributeError as error:
                raise CommandArgumentError(
                    f"Enter a value for '{spec.dest}'. {help_text}"
                ) from error
        else:
            raise CommandArgumentError(
                f"Argument '{spec.dest}' requires a value. Expected {spec.nargs} values. {help_text}"
            )

    async def _handle_token(
        self,
        token: str,
        args: list[str],
        index: int,
        result: dict[str, Any],
        positional_args: list[Argument],
        consumed_positional_indices: set[int],
        consumed_indices: set[int],
        arg_states: dict[str, ArgumentState],
        from_validate: bool = False,
    ) -> int:
        """Handle a single token in the command line arguments."""
        if token in self._keyword:
            spec = self._keyword[token]
            action = spec.action

            if action == ArgumentAction.HELP:
                if not from_validate:
                    self.render_help()
                arg_states[spec.dest].set_consumed()
                raise HelpSignal()
            elif action == ArgumentAction.TLDR:
                if self._is_help_command:
                    result[spec.dest] = True
                    arg_states[spec.dest].set_consumed()
                    consumed_indices.add(index)
                    index += 1
                elif not from_validate:
                    self.render_tldr()
                    arg_states[spec.dest].set_consumed()
                    raise HelpSignal()
                else:
                    arg_states[spec.dest].set_consumed()
                    raise HelpSignal()
            elif action == ArgumentAction.ACTION:
                assert isinstance(
                    spec.resolver, BaseAction
                ), "resolver should be an instance of BaseAction"
                values, new_index = self._consume_nargs(args, index + 1, spec)
                try:
                    typed_values = [coerce_value(value, spec.type) for value in values]
                except ValueError as error:
                    arg_states[spec.dest].reset()
                    arg_states[spec.dest].has_invalid_choice = True
                    raise CommandArgumentError(
                        f"Invalid value for '{spec.dest}': {error}"
                    ) from error
                if not spec.lazy_resolver or not from_validate:
                    try:
                        result[spec.dest] = await spec.resolver(*typed_values)
                    except Exception as error:
                        raise CommandArgumentError(
                            f"[{spec.dest}] Action failed: {error}"
                        ) from error
                self._check_if_in_choices(spec, result, arg_states)
                arg_states[spec.dest].set_consumed(new_index)
                consumed_indices.update(range(index, new_index))
                index = new_index
            elif action == ArgumentAction.STORE_TRUE:
                result[spec.dest] = True
                arg_states[spec.dest].set_consumed(index)
                consumed_indices.add(index)
                index += 1
            elif action == ArgumentAction.STORE_FALSE:
                result[spec.dest] = False
                arg_states[spec.dest].set_consumed(index)
                consumed_indices.add(index)
                index += 1
            elif action == ArgumentAction.STORE_BOOL_OPTIONAL:
                result[spec.dest] = spec.type(True)
                arg_states[spec.dest].set_consumed(index)
                consumed_indices.add(index)
                index += 1
            elif action == ArgumentAction.COUNT:
                result[spec.dest] = result.get(spec.dest, 0) + 1
                consumed_indices.add(index)
                index += 1
            elif action == ArgumentAction.APPEND:
                assert result.get(spec.dest) is not None, "dest should not be None"
                values, new_index = self._consume_nargs(args, index + 1, spec)
                try:
                    typed_values = [coerce_value(value, spec.type) for value in values]
                except ValueError as error:
                    arg_states[spec.dest].reset()
                    arg_states[spec.dest].has_invalid_choice = True
                    raise CommandArgumentError(
                        f"Invalid value for '{spec.dest}': {error}"
                    ) from error
                if not typed_values:
                    self._raise_suggestion_error(spec)
                if spec.nargs is None:
                    result[spec.dest].append(spec.type(typed_values[0]))
                else:
                    result[spec.dest].append(typed_values)
                consumed_indices.update(range(index, new_index))
                index = new_index
            elif action == ArgumentAction.EXTEND:
                assert result.get(spec.dest) is not None, "dest should not be None"
                values, new_index = self._consume_nargs(args, index + 1, spec)
                try:
                    typed_values = [coerce_value(value, spec.type) for value in values]
                except ValueError as error:
                    arg_states[spec.dest].reset()
                    arg_states[spec.dest].has_invalid_choice = True
                    raise CommandArgumentError(
                        f"Invalid value for '{spec.dest}': {error}"
                    ) from error
                result[spec.dest].extend(typed_values)
                consumed_indices.update(range(index, new_index))
                index = new_index
            else:
                values, new_index = self._consume_nargs(args, index + 1, spec)
                try:
                    typed_values = [coerce_value(value, spec.type) for value in values]
                except ValueError as error:
                    arg_states[spec.dest].reset()
                    arg_states[spec.dest].has_invalid_choice = True
                    raise CommandArgumentError(
                        f"Invalid value for '{spec.dest}': {error}"
                    ) from error
                if not typed_values and spec.nargs not in ("*", "?"):
                    self._raise_suggestion_error(spec)
                if spec.nargs in (None, 1, "?"):
                    result[spec.dest] = (
                        typed_values[0] if len(typed_values) == 1 else typed_values
                    )
                else:
                    result[spec.dest] = typed_values
                self._check_if_in_choices(spec, result, arg_states)
                arg_states[spec.dest].set_consumed(new_index)
                consumed_indices.update(range(index, new_index))
                index = new_index
        elif token.startswith("-") and not self._is_valid_dash_token_positional_value(
            token
        ):
            self._raise_remaining_args_error(token, arg_states)
        else:
            # Get the next flagged argument index if it exists
            next_flagged_index = -1
            for scan_index, arg in enumerate(args[index:], start=index):
                if arg in self._keyword:
                    next_flagged_index = scan_index
                    break
            if next_flagged_index == -1:
                next_flagged_index = len(args)
            args_consumed = await self._consume_all_positional_args(
                args[index:next_flagged_index],
                result,
                positional_args,
                consumed_positional_indices,
                arg_states=arg_states,
                from_validate=from_validate,
                base_index=index,
            )
            index += args_consumed
        return index

    def _find_last_flag_argument(self, args: list[str]) -> Argument | None:
        """Find the last flag argument in the provided args."""
        last_flag_argument = None
        for arg in reversed(args):
            if arg in self._keyword:
                last_flag_argument = self._keyword[arg]
                break
        return last_flag_argument

    def _resolve_posix_bundling(self, args: list[str]) -> None:
        """Expand POSIX-style bundled arguments into separate arguments."""
        last_flag_argument: Argument | None = None
        expand_index = 0
        while expand_index < len(args):
            last_flag_argument = self._find_last_flag_argument(args[:expand_index])
            expand_token = self._expand_posix_bundling(
                args[expand_index], last_flag_argument
            )
            if isinstance(expand_token, list):
                args[expand_index : expand_index + 1] = expand_token
            expand_index += len(expand_token) if isinstance(expand_token, list) else 1

    def _is_present(self, spec: Argument, value: Any) -> bool:
        """
        Presence means 'user actually selected/provided this', not merely that
        a default exists.
        """
        if spec.action == ArgumentAction.STORE_TRUE:
            return value is True
        if spec.action == ArgumentAction.STORE_FALSE:
            return value is False
        if spec.action == ArgumentAction.STORE_BOOL_OPTIONAL:
            return value is not None
        if spec.action == ArgumentAction.COUNT:
            return bool(value)
        if spec.action in (ArgumentAction.APPEND, ArgumentAction.EXTEND):
            return bool(value)
        return value is not None

    def _validate_mutex_groups(self, result: dict[str, Any]) -> None:
        for group in self._mutex_groups.values():
            present: list[str] = []

            for dest in group.dests:
                spec = self.get_argument(dest)
                if spec is None:
                    continue
                if self._is_present(spec, result.get(dest)):
                    present.append(dest)

            if len(present) > 1:
                raise CommandArgumentError(
                    f"Arguments in mutually exclusive group '{group.name}' "
                    f"cannot be used together: {', '.join(present)}"
                )

            if group.required and not present:
                members = []
                for dest in group.dests:
                    spec = self.get_argument(dest)
                    if spec:
                        members.append(spec.flags[0] if spec.flags else dest)
                raise CommandArgumentError(
                    f"One of the following is required for group '{group.name}': "
                    f"{', '.join(members)}"
                )

    async def parse_args(
        self, args: list[str] | None = None, from_validate: bool = False
    ) -> dict[str, Any]:
        """Parse CLI arguments into a resolved mapping of values.

        This method parses the provided CLI-style tokens and returns a dictionary
        mapping argument destinations to their resolved values. It performs full
        validation, type coercion, default handling, and resolver execution.

        Unlike `parse_args_split`, this method returns a unified mapping of all
        parsed arguments, including both command arguments and execution options.

        Behavior:
        - Parses positional and keyword arguments based on registered definitions
        - Applies type coercion via configured `type` handlers
        - Resolves values using BaseAction resolvers (if defined)
        - Validates required arguments, choices, and mutual exclusion constraints
        - Applies default values for missing optional arguments
        - Supports validation mode (`from_validate=True`) for interactive contexts

        Args:
            args (list[str]): CLI-style argument tokens to parse.
            from_validate (bool): Whether parsing is occurring in validation mode
                (e.g. prompt_toolkit validator). When True, may defer certain
                resolution steps or suppress eager failures.

        Returns:
            dict[str, Any]: Mapping of argument destination names to resolved values.

        Raises:
            CommandArgumentError: If parsing, validation, or coercion fails.
            HelpSignal: If help or TLDR output is triggered during parsing.

        Notes:
            - This method returns a flat mapping of all arguments.
            - Use `parse_args_split` when separating execution options from
            command arguments is required for execution.
            - This is the primary parsing entrypoint used internally by
            `parse_args_split`.
        """
        if args is None:
            args = []

        arg_states = {arg.dest: ArgumentState(arg) for arg in self._arguments}
        self._last_positional_states = {
            arg.dest: arg_states[arg.dest] for arg in self._positional.values()
        }
        self._last_keyword_states = {
            arg.dest: arg_states[arg.dest] for arg in self._keyword_list
        }

        result = {arg.dest: deepcopy(arg.default) for arg in self._arguments}
        positional_args: list[Argument] = [
            arg for arg in self._arguments if arg.positional
        ]
        consumed_positional_indices: set[int] = set()
        consumed_indices: set[int] = set()

        self._resolve_posix_bundling(args)

        index = 0
        while index < len(args):
            token = args[index]
            index = await self._handle_token(
                token,
                args,
                index,
                result,
                positional_args,
                consumed_positional_indices,
                consumed_indices,
                arg_states=arg_states,
                from_validate=from_validate,
            )

        # Compare length of args with length of required positional arguments to catch missing required positionals
        if len(args) < len(
            [
                arg
                for arg in self._arguments
                if (arg.positional and arg.required and not arg.default)
            ]
        ):
            missing_positionals = [
                arg.dest
                for arg in self._arguments
                if arg.positional
                and arg.required
                and arg.dest not in consumed_positional_indices
                and not arg.default
            ]
            if missing_positionals:
                raise CommandArgumentError(
                    f"Missing positional argument(s): {', '.join(missing_positionals)}"
                )

        # Required validation
        for spec in self._arguments:
            if spec.dest == "help" or spec.dest == "tldr":
                continue
            if spec.required and result.get(spec.dest) is None:
                help_text = f" help: {spec.help}" if spec.help else ""
                if (
                    spec.action == ArgumentAction.ACTION
                    and spec.lazy_resolver
                    and from_validate
                ):
                    if not args:
                        arg_states[spec.dest].reset()
                        raise CommandArgumentError(
                            f"Missing required argument '{spec.dest}': {spec.get_choice_text()}{help_text}"
                        )
                    continue  # Lazy resolvers are not validated here
                arg_states[spec.dest].reset()
                raise CommandArgumentError(
                    f"Missing required argument '{spec.dest}': {spec.get_choice_text()}{help_text}"
                )

            self._check_if_in_choices(spec, result, arg_states)

            if spec.action == ArgumentAction.ACTION:
                continue

            if isinstance(spec.nargs, int) and spec.nargs > 1:
                assert isinstance(
                    result.get(spec.dest), list
                ), f"Invalid value for '{spec.dest}': expected a list"
                if not result[spec.dest] and not spec.required:
                    continue
                if spec.action == ArgumentAction.APPEND:
                    for group in result[spec.dest]:
                        if len(group) % spec.nargs != 0:
                            arg_states[spec.dest].reset()
                            raise CommandArgumentError(
                                f"Invalid number of values for '{spec.dest}': expected a multiple of {spec.nargs}"
                            )
                elif spec.action == ArgumentAction.EXTEND:
                    if len(result[spec.dest]) % spec.nargs != 0:
                        arg_states[spec.dest].reset()
                        raise CommandArgumentError(
                            f"Invalid number of values for '{spec.dest}': expected a multiple of {spec.nargs}"
                        )
                elif len(result[spec.dest]) != spec.nargs:
                    arg_states[spec.dest].reset()
                    raise CommandArgumentError(
                        f"Invalid number of values for '{spec.dest}': expected {spec.nargs}, got {len(result[spec.dest])}"
                    )

            if isinstance(spec.nargs, str) and spec.nargs == "+":
                assert isinstance(
                    result.get(spec.dest), list
                ), f"Invalid value for '{spec.dest}': expected a list"
                if not result[spec.dest] and not spec.required:
                    continue
                help_text = f" help: {spec.help}" if spec.help else ""
                if not result[spec.dest]:
                    arg_states[spec.dest].reset()
                    raise CommandArgumentError(
                        f"Argument '{spec.dest}' requires at least one value{help_text}"
                    )

        self._validate_mutex_groups(result)

        result.pop("help", None)
        if not self._is_help_command:
            result.pop("tldr", None)
        return result

    async def parse_args_split(
        self, args: list[str], from_validate: bool = False
    ) -> tuple[tuple[Any, ...], dict[str, Any], dict[str, Any]]:
        """Parse arguments and split them into execution-ready components.

        This method parses the provided CLI-style tokens and separates the resolved
        values into three categories:

        - positional arguments for `*args`
        - keyword arguments for `**kwargs`
        - execution arguments for Falyx runtime behavior

        Execution arguments are options such as retries, confirmation flags, or
        summary output that should not be passed to the underlying action.

        Args:
            args (list[str]): CLI-style argument tokens to parse.
            from_validate (bool): Whether parsing is occurring in validation mode.

        Returns:
            tuple:
                - tuple[Any, ...]: Positional arguments for execution.
                - dict[str, Any]: Keyword arguments for execution.
                - dict[str, Any]: Execution-specific arguments handled by Falyx.
        """
        parsed = await self.parse_args(args, from_validate)
        args_list = []
        kwargs_dict = {}
        execution_dict = {}
        for arg in self._arguments:
            if arg.dest == "help":
                continue
            if arg.dest == "tldr" and not self._is_help_command:
                continue
            if arg.positional:
                args_list.append(parsed[arg.dest])
            elif self._is_execution_dest(arg.dest):
                execution_dict[arg.dest] = parsed[arg.dest]
            else:
                kwargs_dict[arg.dest] = parsed[arg.dest]
        return tuple(args_list), kwargs_dict, execution_dict

    def _suggest_paths(self, stub: str) -> list[str]:
        """Return filesystem path suggestions based on a stub."""
        path = Path(stub or ".").expanduser()
        base_dir = path if path.is_dir() else path.parent
        if not base_dir.exists():
            return []
        completions = []
        for child in base_dir.iterdir():
            name = str(child)
            if child.is_dir():
                name += "/"
            completions.append(name)
        if stub and not path.is_dir():
            completions = [
                completion for completion in completions if completion.startswith(stub)
            ]
        return completions[:100]

    def _is_mid_value(
        self, state: ArgumentState | None, args: list[str], cursor_at_end_of_token: bool
    ) -> bool:
        """Check if the current state is in the middle of consuming a value."""
        if state is None:
            return False
        if cursor_at_end_of_token:
            return False
        if not state.consumed:
            return False
        return state.consumed_position == len(args)

    def _is_invalid_choices_state(
        self,
        state: ArgumentState,
        cursor_at_end_of_token: bool,
        num_args_since_last_keyword: int,
    ) -> bool:
        """Check if the state indicates an invalid choice condition."""
        if isinstance(state.arg.nargs, int):
            return (
                state.has_invalid_choice
                and not state.consumed
                and (
                    num_args_since_last_keyword > state.arg.nargs
                    or (num_args_since_last_keyword >= 1 and cursor_at_end_of_token)
                )
            )
        if state.arg.nargs in ("?", None):
            return (
                state.has_invalid_choice
                and not state.consumed
                and (
                    num_args_since_last_keyword > 1
                    or (num_args_since_last_keyword == 1 and cursor_at_end_of_token)
                )
            )
        return False

    def _value_suggestions_for_arg(
        self,
        state: ArgumentState,
        prefix: str,
        cursor_at_end_of_token: bool,
        num_args_since_last_keyword: int,
    ) -> list[str]:
        """Return a list of value suggestions for the given argument state."""
        if self._is_invalid_choices_state(
            state, cursor_at_end_of_token, num_args_since_last_keyword
        ):
            return []
        arg = state.arg
        suggestion_filter = (
            (lambda _: True)
            if cursor_at_end_of_token
            else (lambda suggestion: (not prefix) or str(suggestion).startswith(prefix))
        )
        if arg.choices:
            return [str(choice) for choice in arg.choices if suggestion_filter(choice)]
        if arg.suggestions:
            return [
                str(suggestion)
                for suggestion in arg.suggestions
                if suggestion_filter(suggestion)
            ]
        if issubclass(arg.type, Path):
            return self._suggest_paths(prefix if not cursor_at_end_of_token else ".")
        return []

    def _filter_mutex_flags(
        self,
        remaining_flags: list[str],
        consumed_dests: list[str],
    ) -> list[str]:
        active_mutex_groups = {
            self._mutex_group_by_dest[dest]
            for dest in consumed_dests
            if dest in self._mutex_group_by_dest
        }

        if not active_mutex_groups:
            return remaining_flags

        filtered: list[str] = []
        for flag in remaining_flags:
            arg = self._keyword[flag]
            mutex_name = self._mutex_group_by_dest.get(arg.dest)
            if (
                mutex_name
                and mutex_name in active_mutex_groups
                and arg.dest not in consumed_dests
            ):
                continue
            filtered.append(flag)

        return filtered

    def suggest_next(
        self, args: list[str], cursor_at_end_of_token: bool = False
    ) -> list[str]:
        """Suggest valid completions for the current argument state.

        This method analyzes the partially entered argument list and returns
        context-aware suggestions for the next token. Suggestions may include:

        - remaining flags
        - valid choices for the current argument
        - configured custom suggestions
        - filesystem paths for `Path`-typed arguments

        It supports positional arguments, flagged arguments, multi-value arguments,
        POSIX short-flag bundling, and mutually exclusive group filtering.

        Args:
            args (list[str]): Current partial argument tokens.
            cursor_at_end_of_token (bool): Whether the cursor is positioned after a
                completed token (for example, after a trailing space).

        Returns:
            list[str]: Sorted completion suggestions valid for the current parse state.
        """
        self._resolve_posix_bundling(args)
        last = args[-1] if args else ""
        # Case 1: Next positional argument
        last_consumed_positional_index = -1
        num_args_since_last_positional = 0
        next_non_consumed_positional_arg: Argument | None = None
        next_non_consumed_positional_state: ArgumentState | None = None
        for state in self._last_positional_states.values():
            if not state.consumed or self._is_mid_value(
                state, args, cursor_at_end_of_token
            ):
                next_non_consumed_positional_arg = state.arg
                next_non_consumed_positional_state = state
                break
            elif state.consumed_position is not None:
                last_consumed_positional_index = max(
                    last_consumed_positional_index, state.consumed_position
                )

        if last_consumed_positional_index != -1:
            num_args_since_last_positional = len(args) - last_consumed_positional_index
        else:
            num_args_since_last_positional = len(args)
        if next_non_consumed_positional_arg and next_non_consumed_positional_state:
            if next_non_consumed_positional_arg.choices:
                if (
                    cursor_at_end_of_token
                    and last
                    and any(
                        str(choice).startswith(last)
                        for choice in next_non_consumed_positional_arg.choices
                    )
                    and next_non_consumed_positional_arg.nargs in (1, "?", None)
                ):
                    return []
                if self._is_invalid_choices_state(
                    next_non_consumed_positional_state,
                    cursor_at_end_of_token,
                    num_args_since_last_positional,
                ):
                    return []
                return sorted(
                    (str(choice) for choice in next_non_consumed_positional_arg.choices)
                )
            if next_non_consumed_positional_arg.suggestions:
                if (
                    cursor_at_end_of_token
                    and last
                    and any(
                        str(suggestion).startswith(last)
                        for suggestion in next_non_consumed_positional_arg.suggestions
                    )
                    and next_non_consumed_positional_arg.nargs in (1, "?", None)
                ):
                    return []
                return sorted(next_non_consumed_positional_arg.suggestions)
            if issubclass(next_non_consumed_positional_arg.type, Path):
                if cursor_at_end_of_token:
                    return self._suggest_paths(".")
                else:
                    return self._suggest_paths(args[-1] if args else ".")

        consumed_dests = [
            state.arg.dest
            for state in self._last_keyword_states.values()
            if state.consumed
        ]

        remaining_flags = [
            flag for flag, arg in self._keyword.items() if arg.dest not in consumed_dests
        ]
        remaining_flags = self._filter_mutex_flags(remaining_flags, consumed_dests)

        last_keyword_state_in_args = None
        last_keyword = None
        for last_arg in reversed(args):
            if last_arg in self._keyword:
                last_keyword_state_in_args = self._last_keyword_states.get(
                    self._keyword[last_arg].dest
                )
                last_keyword = last_arg
                break
        num_args_since_last_keyword = (
            len(args) - 1 - args.index(last_keyword) if last_keyword else 0
        )

        next_to_last = args[-2] if len(args) > 1 else ""
        suggestions: list[str] = []
        # Case 2: Mid-flag (e.g., "--ver")
        if last.startswith("-") and last not in self._keyword:
            if last_keyword_state_in_args and (
                not last_keyword_state_in_args.consumed
                or self._is_mid_value(
                    last_keyword_state_in_args, args, cursor_at_end_of_token
                )
            ):
                # Previous keyword still needs values (or we're mid-value) → suggest values for it.
                suggestions.extend(
                    self._value_suggestions_for_arg(
                        last_keyword_state_in_args,
                        last,
                        cursor_at_end_of_token,
                        num_args_since_last_keyword,
                    )
                )
                if (
                    last_keyword_state_in_args.arg.action
                    in (
                        ArgumentAction.APPEND,
                        ArgumentAction.EXTEND,
                        ArgumentAction.COUNT,
                    )
                    and next_to_last not in self._keyword
                ):
                    suggestions.extend(
                        flag for flag in remaining_flags if flag.startswith(last)
                    )
            elif not cursor_at_end_of_token:
                # Suggest all flags that start with the last token
                suggestions.extend(
                    flag for flag in remaining_flags if flag.startswith(last)
                )
            else:
                # If space at end of token, suggest all remaining flags
                suggestions.extend(flag for flag in remaining_flags)

            if (
                last_keyword_state_in_args
                and last_keyword_state_in_args.consumed
                and last_keyword_state_in_args.arg.nargs in ("*", "?")
            ):
                suggestions.extend(
                    flag for flag in remaining_flags if flag.startswith(last)
                )
        # Case 3: Flag that expects a value (e.g., ["--tag"])
        elif last in self._keyword and last_keyword_state_in_args:
            arg = last_keyword_state_in_args.arg
            if last_keyword_state_in_args.consumed and not cursor_at_end_of_token:
                # If last flag is already consumed, (e.g., ["--verbose"])
                # and space not at end of token, suggest nothing.
                pass
            elif (
                last_keyword_state_in_args.consumed
                and cursor_at_end_of_token
                and last_keyword_state_in_args.arg.nargs not in ("*", "?")
            ):
                # space at end of token, suggest remaining flags
                suggestions.extend(flag for flag in remaining_flags)
            else:
                suggestions.extend(
                    self._value_suggestions_for_arg(
                        last_keyword_state_in_args,
                        last,
                        cursor_at_end_of_token,
                        num_args_since_last_keyword,
                    )
                )
        # Case 4: Last flag with choices mid-choice (e.g., ["--tag", "v"])
        elif next_to_last in self._keyword and last_keyword_state_in_args:
            arg = last_keyword_state_in_args.arg
            if self._is_mid_value(
                last_keyword_state_in_args,
                args,
                cursor_at_end_of_token,
            ):
                suggestions.extend(
                    self._value_suggestions_for_arg(
                        last_keyword_state_in_args,
                        last,
                        cursor_at_end_of_token,
                        num_args_since_last_keyword,
                    )
                )
            elif (
                last_keyword_state_in_args.consumed
                and last_keyword_state_in_args
                and Counter(args)[next_to_last]
                > (
                    last_keyword_state_in_args.arg.nargs
                    if isinstance(last_keyword_state_in_args.arg.nargs, int)
                    else 1
                )
            ):
                pass
            elif arg.choices and last not in arg.choices and not cursor_at_end_of_token:
                suggestions.extend(
                    (str(choice) for choice in arg.choices if choice.startswith(last))
                )
            elif (
                arg.suggestions
                and last not in arg.suggestions
                and not any(last.startswith(suggestion) for suggestion in arg.suggestions)
                and any(suggestion.startswith(last) for suggestion in arg.suggestions)
                and not cursor_at_end_of_token
            ):
                suggestions.extend(
                    (
                        str(suggestion)
                        for suggestion in arg.suggestions
                        if suggestion.startswith(last)
                    )
                )
            elif issubclass(arg.type, Path) and not cursor_at_end_of_token:
                suggestions.extend(self._suggest_paths(last))
            elif last_keyword_state_in_args and not last_keyword_state_in_args.consumed:
                suggestions.extend(
                    self._value_suggestions_for_arg(
                        last_keyword_state_in_args,
                        last,
                        cursor_at_end_of_token,
                        num_args_since_last_keyword,
                    )
                )
                if (
                    last_keyword_state_in_args.arg.action
                    in (
                        ArgumentAction.APPEND,
                        ArgumentAction.EXTEND,
                        ArgumentAction.COUNT,
                    )
                    and last not in self._keyword
                ):
                    suggestions.extend(flag for flag in remaining_flags)
            else:
                suggestions.extend(remaining_flags)
        # Case 5: Last flag is incomplete and expects a value (e.g., ["--tag", "value1", "va"])
        elif last_keyword_state_in_args and not last_keyword_state_in_args.consumed:
            suggestions.extend(
                self._value_suggestions_for_arg(
                    last_keyword_state_in_args,
                    last,
                    cursor_at_end_of_token,
                    num_args_since_last_keyword,
                )
            )
        # Case 6: Last keyword state is mid-value (e.g., ["--tag", "value1", "va"]) but consumed
        elif self._is_mid_value(last_keyword_state_in_args, args, cursor_at_end_of_token):
            if not last_keyword_state_in_args:
                pass
            else:
                suggestions.extend(
                    self._value_suggestions_for_arg(
                        last_keyword_state_in_args,
                        last,
                        cursor_at_end_of_token,
                        num_args_since_last_keyword,
                    )
                )
        # Case 7: Suggest all remaining flags
        else:
            suggestions.extend(remaining_flags)

        # Case 8: Last keyword state is a multi-value argument
        #         (e.g., ["--tags", "value1", "value2", "va"])
        #         and it accepts multiple values
        #         (e.g., nargs='*', nargs='+')
        if last_keyword_state_in_args:
            if last_keyword_state_in_args.arg.nargs in ("*", "+"):
                suggestions.extend(
                    self._value_suggestions_for_arg(
                        last_keyword_state_in_args,
                        last,
                        cursor_at_end_of_token,
                        num_args_since_last_keyword,
                    )
                )

        return sorted(set(suggestions))

    def get_options_text(self, plain_text=False) -> str:
        """
        Render all defined arguments as a help-style string.

        Returns:
            str: A visual description of argument flags and structure.
        """
        # Options
        # Add all keyword arguments to the options list
        options_list = []
        for arg in self._keyword_list:
            choice_text = arg.get_choice_text()
            if choice_text:
                options_list.extend([f"[{arg.flags[0]} {choice_text}]"])
            else:
                options_list.extend([f"[{arg.flags[0]}]"])

        # Add positional arguments to the options list
        for arg in self._positional.values():
            choice_text = arg.get_choice_text()
            if isinstance(arg.nargs, int):
                choice_text = " ".join([choice_text] * arg.nargs)
            if plain_text:
                options_list.append(choice_text)
            else:
                options_list.append(escape(choice_text))

        return " ".join(options_list)

    def get_command_keys_text(self, plain_text=False) -> str:
        """
        Return formatted string showing the command key and aliases.

        Used in help rendering and introspection.

        Returns:
            str: The visual command selector line.
        """
        if plain_text:
            command_keys = " | ".join(
                [f"{self.command_key}"] + [f"{alias}" for alias in self.aliases]
            )
        else:
            command_keys = " | ".join(
                [f"[{self.command_style}]{self.command_key}[/{self.command_style}]"]
                + [
                    f"[{self.command_style}]{alias}[/{self.command_style}]"
                    for alias in self.aliases
                ]
            )
        return command_keys

    def get_usage(self, plain_text=False) -> str:
        """
        Render the usage string for this parser.

        Returns:
            str: A formatted usage line showing syntax and argument structure.
        """
        command_keys = self.get_command_keys_text(plain_text)
        options_text = self.get_options_text(plain_text)
        if options_text:
            if self.options_manager.get("mode") == FalyxMode.MENU:
                return f"{command_keys} {options_text}"
            else:
                program = self.program or "falyx"
                program_style = (
                    self.options_manager.get("program_style") or self.command_style
                )
                return f"[{program_style}]{program}[/{program_style}] {command_keys} {options_text}"
        return command_keys

    def _iter_keyword_help_sections(
        self,
    ) -> Generator[tuple[str, str, list[Argument]], None, None]:
        """
        Yields (title, description, arguments)
        """
        assigned = set()

        for group in self._argument_groups.values():
            args = []
            for dest in group.dests:
                spec = self.get_argument(dest)
                if spec and not spec.positional:
                    args.append(spec)
                    assigned.add(dest)
            if args:
                yield group.name, group.description, args

        ungrouped = []
        for arg in self._keyword_list:
            if arg.dest not in assigned:
                ungrouped.append(arg)

        if ungrouped:
            yield "options", "", ungrouped

    def render_help(self) -> None:
        """Render full help output for the command.

        This method displays a complete help view for the command, including
        usage, description, argument definitions, execution options, and any
        additional help text.

        The output is formatted using Rich and is intended for both CLI and
        interactive menu contexts.

        Behavior:
        - Renders a usage string derived from the parser configuration
        - Displays command description, aliases, and optional epilog text
        - Lists positional and keyword arguments with types, defaults, and help text
        - Supports argument grouping and mutually exclusive groups
        - Applies styling based on configured command style
        """
        usage = self.get_usage()
        self.console.print(f"[bold]usage: {usage}[/bold]\n")

        if self.help_text:
            self.console.print(self.help_text + "\n")

        if self._arguments:
            if self._positional:
                self.console.print("[bold]positional:[/bold]")
                for arg in self._positional.values():
                    flags = arg.get_positional_text()
                    arg_line = f"  {flags:<30} "
                    help_text = arg.help or ""
                    if help_text and len(flags) > 30:
                        help_text = f"\n{'':<33}{help_text}"
                    self.console.print(f"{arg_line}{help_text}")

            for title, description, args in self._iter_keyword_help_sections():
                self.console.print(f"\n[bold]{title}:[/bold]")
                if description:
                    self.console.print(f"  [dim]{description}[/dim]")

                arg_groups: defaultdict[str, list[Argument]] = defaultdict(list)
                for arg in args:
                    arg_groups[arg.dest].append(arg)

                for group in arg_groups.values():
                    if len(group) == 2 and all(
                        arg.action == ArgumentAction.STORE_BOOL_OPTIONAL for arg in group
                    ):
                        # Merge --flag / --no-flag pair into single help line for STORE_BOOL_OPTIONAL
                        all_flags = tuple(
                            sorted(
                                (arg.flags[0] for arg in group),
                                key=lambda f: f.startswith("--no-"),
                            )
                        )
                    else:
                        all_flags = group[0].flags

                    suffix = ""
                    mutex_name = group[0].mutex_group
                    if mutex_name:
                        suffix = f" [dim]({mutex_name})[/dim]"
                    flags = ", ".join(all_flags)
                    flags_choice = f"{flags} {group[0].get_choice_text()}"
                    arg_line = f"  {flags_choice:<30} "
                    help_text = f"{group[0].help or ''}{suffix}"
                    if help_text and len(flags_choice) > 30:
                        help_text = f"\n{'':<33}{help_text}"
                    self.console.print(f"{arg_line}{help_text}")

        if self.help_epilog:
            self.console.print("\n" + self.help_epilog, style="dim")

    def render_tldr(self) -> None:
        """Render concise example usage (TLDR) for the command.

        This method displays a minimal, example-driven view of how to invoke
        the command. It is intended as a quick-start reference rather than a
        complete specification.

        Notes:
            - TLDR output is designed for speed and clarity, not completeness.
            - Typically invoked via `--tldr` or equivalent help flags.
            - Complements `render_help`, which provides full documentation.
        """
        if not self._tldr_examples:
            self.console.print(
                f"[bold]No TLDR examples available for {self.command_key}.[/bold]"
            )
            return
        is_cli_mode = self.options_manager.get("mode") != FalyxMode.MENU
        program = self.program or "falyx"
        program_style = self.options_manager.get("program_style") or self.command_style
        command = self.aliases[0] if self.aliases else self.command_key
        if self._is_help_command and is_cli_mode:
            command = f"[{program_style}]{program}[/{program_style}] [{self.command_style}]help[/{self.command_style}]"
        elif is_cli_mode:
            command = f"[{program_style}]{program}[/{program_style}] [{self.command_style}]{command}[/{self.command_style}]"
        else:
            command = f"[{self.command_style}]{command}[/{self.command_style}]"

        usage = self.get_usage()
        self.console.print(f"[bold]usage:[/] {usage}\n")

        if self.help_text:
            self.console.print(f"{self.help_text}\n")

        self.console.print("[bold]examples:[/bold]")
        for example in self._tldr_examples:
            usage = f"{command} {example.usage.strip()}"
            description = example.description.strip()
            block = f"[bold]{usage}[/bold]"
            self.console.print(
                Padding(
                    Panel(block, expand=False, title=description, title_align="left"),
                    (0, 2),
                )
            )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CommandArgumentParser):
            return False

        def sorted_args(parser):
            return sorted(parser._arguments, key=lambda a: a.dest)

        return sorted_args(self) == sorted_args(other)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._arguments, key=lambda a: a.dest)))

    def __str__(self) -> str:
        """Return a human-readable summary of the parser state."""
        positional = sum(arg.positional for arg in self._arguments)
        required = sum(arg.required for arg in self._arguments)
        return (
            f"CommandArgumentParser(args={len(self._arguments)}, "
            f"flags={len(self._flag_map)}, keywords={len(self._keyword)}, "
            f"positional={positional}, required={required})"
        )

    def __repr__(self) -> str:
        return str(self)
