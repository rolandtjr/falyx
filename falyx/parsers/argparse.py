# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from rich.console import Console
from rich.markup import escape
from rich.text import Text

from falyx.action.base import BaseAction
from falyx.exceptions import CommandArgumentError
from falyx.signals import HelpSignal


class ArgumentAction(Enum):
    """Defines the action to be taken when the argument is encountered."""

    ACTION = "action"
    STORE = "store"
    STORE_TRUE = "store_true"
    STORE_FALSE = "store_false"
    APPEND = "append"
    EXTEND = "extend"
    COUNT = "count"
    HELP = "help"

    @classmethod
    def choices(cls) -> list[ArgumentAction]:
        """Return a list of all argument actions."""
        return list(cls)

    def __str__(self) -> str:
        """Return the string representation of the argument action."""
        return self.value


@dataclass
class Argument:
    """Represents a command-line argument."""

    flags: tuple[str, ...]
    dest: str  # Destination name for the argument
    action: ArgumentAction = (
        ArgumentAction.STORE
    )  # Action to be taken when the argument is encountered
    type: Any = str  # Type of the argument (e.g., str, int, float) or callable
    default: Any = None  # Default value if the argument is not provided
    choices: list[str] | None = None  # List of valid choices for the argument
    required: bool = False  # True if the argument is required
    help: str = ""  # Help text for the argument
    nargs: int | str | None = None  # int, '?', '*', '+', None
    positional: bool = False  # True if no leading - or -- in flags
    resolver: BaseAction | None = None  # Action object for the argument

    def get_positional_text(self) -> str:
        """Get the positional text for the argument."""
        text = ""
        if self.positional:
            if self.choices:
                text = f"{{{','.join([str(choice) for choice in self.choices])}}}"
            else:
                text = self.dest
        return text

    def get_choice_text(self) -> str:
        """Get the choice text for the argument."""
        choice_text = ""
        if self.choices:
            choice_text = f"{{{','.join([str(choice) for choice in self.choices])}}}"
        elif (
            self.action
            in (
                ArgumentAction.STORE,
                ArgumentAction.APPEND,
                ArgumentAction.EXTEND,
            )
            and not self.positional
        ):
            choice_text = self.dest.upper()
        elif self.action in (
            ArgumentAction.STORE,
            ArgumentAction.APPEND,
            ArgumentAction.EXTEND,
        ) or isinstance(self.nargs, str):
            choice_text = self.dest

        if self.nargs == "?":
            choice_text = f"[{choice_text}]"
        elif self.nargs == "*":
            choice_text = f"[{choice_text} ...]"
        elif self.nargs == "+":
            choice_text = f"{choice_text} [{choice_text} ...]"
        return choice_text

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Argument):
            return False
        return (
            self.flags == other.flags
            and self.dest == other.dest
            and self.action == other.action
            and self.type == other.type
            and self.choices == other.choices
            and self.required == other.required
            and self.nargs == other.nargs
            and self.positional == other.positional
            and self.default == other.default
            and self.help == other.help
        )

    def __hash__(self) -> int:
        return hash(
            (
                tuple(self.flags),
                self.dest,
                self.action,
                self.type,
                tuple(self.choices or []),
                self.required,
                self.nargs,
                self.positional,
                self.default,
                self.help,
            )
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
    - Exception handling for invalid arguments.
    - Render Help using Rich library.
    """

    def __init__(
        self,
        command_key: str = "",
        command_description: str = "",
        command_style: str = "bold",
        help_text: str = "",
        help_epilogue: str = "",
        aliases: list[str] | None = None,
    ) -> None:
        """Initialize the CommandArgumentParser."""
        self.console = Console(color_system="auto")
        self.command_key: str = command_key
        self.command_description: str = command_description
        self.command_style: str = command_style
        self.help_text: str = help_text
        self.help_epilogue: str = help_epilogue
        self.aliases: list[str] = aliases or []
        self._arguments: list[Argument] = []
        self._positional: dict[str, Argument] = {}
        self._keyword: dict[str, Argument] = {}
        self._keyword_list: list[Argument] = []
        self._flag_map: dict[str, Argument] = {}
        self._dest_set: set[str] = set()
        self._add_help()

    def _add_help(self):
        """Add help argument to the parser."""
        self.add_argument(
            "-h",
            "--help",
            action=ArgumentAction.HELP,
            help="Show this help message.",
            dest="help",
        )

    def _is_positional(self, flags: tuple[str, ...]) -> bool:
        """Check if the flags are positional."""
        positional = False
        if any(not flag.startswith("-") for flag in flags):
            positional = True

        if positional and len(flags) > 1:
            raise CommandArgumentError("Positional arguments cannot have multiple flags")
        return positional

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
        self, required: bool, positional: bool, nargs: int | str | None
    ) -> bool:
        """Determine if the argument is required."""
        if required:
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
        if action in (
            ArgumentAction.STORE_FALSE,
            ArgumentAction.STORE_TRUE,
            ArgumentAction.COUNT,
            ArgumentAction.HELP,
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
        self, choices: Iterable | None, expected_type: Any
    ) -> list[Any]:
        if choices is not None:
            if isinstance(choices, dict):
                raise CommandArgumentError("choices cannot be a dict")
            try:
                choices = list(choices)
            except TypeError:
                raise CommandArgumentError(
                    "choices must be iterable (like list, tuple, or set)"
                )
        else:
            choices = []
        for choice in choices:
            if not isinstance(choice, expected_type):
                try:
                    expected_type(choice)
                except Exception:
                    raise CommandArgumentError(
                        f"Invalid choice {choice!r}: not coercible to {expected_type.__name__}"
                    )
        return choices

    def _validate_default_type(
        self, default: Any, expected_type: type, dest: str
    ) -> None:
        """Validate the default value type."""
        if default is not None and not isinstance(default, expected_type):
            try:
                expected_type(default)
            except Exception:
                raise CommandArgumentError(
                    f"Default value {default!r} for '{dest}' cannot be coerced to {expected_type.__name__}"
                )

    def _validate_default_list_type(
        self, default: list[Any], expected_type: type, dest: str
    ) -> None:
        if isinstance(default, list):
            for item in default:
                if not isinstance(item, expected_type):
                    try:
                        expected_type(item)
                    except Exception:
                        raise CommandArgumentError(
                            f"Default list value {default!r} for '{dest}' cannot be coerced to {expected_type.__name__}"
                        )

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
        if not isinstance(action, ArgumentAction):
            try:
                action = ArgumentAction(action)
            except ValueError:
                raise CommandArgumentError(
                    f"Invalid action '{action}' is not a valid ArgumentAction"
                )
        if action in (
            ArgumentAction.STORE_TRUE,
            ArgumentAction.STORE_FALSE,
            ArgumentAction.COUNT,
            ArgumentAction.HELP,
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
    ) -> None:
        """Add an argument to the parser.
        For `ArgumentAction.ACTION`, `nargs` and `type` determine how many and what kind
        of inputs are passed to the `resolver`.

        The return value of the `resolver` is used directly (no type coercion is applied).
        Validation, structure, and post-processing should be handled within the `resolver`.

        Args:
            name or flags: Either a name or prefixed flags (e.g. 'faylx', '-f', '--falyx').
            action: The action to be taken when the argument is encountered.
            nargs: The number of arguments expected.
            default: The default value if the argument is not provided.
            type: The type to which the command-line argument should be converted.
            choices: A container of the allowable values for the argument.
            required: Whether or not the argument is required.
            help: A brief description of the argument.
            dest: The name of the attribute to be added to the object returned by parse_args().
            resolver: A BaseAction called with optional nargs specified parsed arguments.
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
        choices = self._normalize_choices(choices, expected_type)
        if default is not None and choices and default not in choices:
            raise CommandArgumentError(
                f"Default value '{default}' not in allowed choices: {choices}"
            )
        required = self._determine_required(required, positional, nargs)
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
        )
        for flag in flags:
            if flag in self._flag_map:
                existing = self._flag_map[flag]
                raise CommandArgumentError(
                    f"Flag '{flag}' is already used by argument '{existing.dest}'"
                )
        for flag in flags:
            self._flag_map[flag] = argument
            if not positional:
                self._keyword[flag] = argument
        self._dest_set.add(dest)
        self._arguments.append(argument)
        if positional:
            self._positional[dest] = argument
        else:
            self._keyword_list.append(argument)

    def get_argument(self, dest: str) -> Argument | None:
        return next((a for a in self._arguments if a.dest == dest), None)

    def to_definition_list(self) -> list[dict[str, Any]]:
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
                }
            )
        return defs

    def _consume_nargs(
        self, args: list[str], start: int, spec: Argument
    ) -> tuple[list[str], int]:
        assert (
            spec.nargs is None
            or isinstance(spec.nargs, int)
            or isinstance(spec.nargs, str)
            and spec.nargs in ("+", "*", "?")
        ), f"Invalid nargs value: {spec.nargs}"
        values = []
        i = start
        if isinstance(spec.nargs, int):
            values = args[i : i + spec.nargs]
            return values, i + spec.nargs
        elif spec.nargs == "+":
            if i >= len(args):
                raise CommandArgumentError(
                    f"Expected at least one value for '{spec.dest}'"
                )
            while i < len(args) and not args[i].startswith("-"):
                values.append(args[i])
                i += 1
            assert values, "Expected at least one value for '+' nargs: shouldn't happen"
            return values, i
        elif spec.nargs == "*":
            while i < len(args) and not args[i].startswith("-"):
                values.append(args[i])
                i += 1
            return values, i
        elif spec.nargs == "?":
            if i < len(args) and not args[i].startswith("-"):
                return [args[i]], i + 1
            return [], i
        elif spec.nargs is None:
            if i < len(args) and not args[i].startswith("-"):
                return [args[i]], i + 1
            return [], i
        assert False, "Invalid nargs value: shouldn't happen"

    async def _consume_all_positional_args(
        self,
        args: list[str],
        result: dict[str, Any],
        positional_args: list[Argument],
        consumed_positional_indicies: set[int],
    ) -> int:
        remaining_positional_args = [
            (j, spec)
            for j, spec in enumerate(positional_args)
            if j not in consumed_positional_indicies
        ]
        i = 0

        for j, spec in remaining_positional_args:
            # estimate how many args the remaining specs might need
            is_last = j == len(positional_args) - 1
            remaining = len(args) - i
            min_required = 0
            for next_spec in positional_args[j + 1 :]:
                assert (
                    next_spec.nargs is None
                    or isinstance(next_spec.nargs, int)
                    or isinstance(next_spec.nargs, str)
                    and next_spec.nargs in ("+", "*", "?")
                ), f"Invalid nargs value: {spec.nargs}"
                if next_spec.nargs is None:
                    min_required += 1
                elif isinstance(next_spec.nargs, int):
                    min_required += next_spec.nargs
                elif next_spec.nargs == "+":
                    min_required += 1
                elif next_spec.nargs == "?":
                    min_required += 0
                elif next_spec.nargs == "*":
                    min_required += 0

            slice_args = args[i:] if is_last else args[i : i + (remaining - min_required)]
            values, new_i = self._consume_nargs(slice_args, 0, spec)
            i += new_i

            try:
                typed = [spec.type(v) for v in values]
            except Exception:
                raise CommandArgumentError(
                    f"Invalid value for '{spec.dest}': expected {spec.type.__name__}"
                )
            if spec.action == ArgumentAction.ACTION:
                assert isinstance(
                    spec.resolver, BaseAction
                ), "resolver should be an instance of BaseAction"
                try:
                    result[spec.dest] = await spec.resolver(*typed)
                except Exception as error:
                    raise CommandArgumentError(
                        f"[{spec.dest}] Action failed: {error}"
                    ) from error
            elif spec.action == ArgumentAction.APPEND:
                assert result.get(spec.dest) is not None, "dest should not be None"
                if spec.nargs is None:
                    result[spec.dest].append(typed[0])
                else:
                    result[spec.dest].append(typed)
            elif spec.action == ArgumentAction.EXTEND:
                assert result.get(spec.dest) is not None, "dest should not be None"
                result[spec.dest].extend(typed)
            elif spec.nargs in (None, 1, "?"):
                result[spec.dest] = typed[0] if len(typed) == 1 else typed
            else:
                result[spec.dest] = typed

            if spec.nargs not in ("*", "+"):
                consumed_positional_indicies.add(j)

        if i < len(args):
            raise CommandArgumentError(f"Unexpected positional argument: {args[i:]}")

        return i

    def _expand_posix_bundling(self, args: list[str]) -> list[str]:
        """Expand POSIX-style bundled arguments into separate arguments."""
        expanded = []
        for token in args:
            if token.startswith("-") and not token.startswith("--") and len(token) > 2:
                # POSIX bundle
                # e.g. -abc -> -a -b -c
                for char in token[1:]:
                    flag = f"-{char}"
                    arg = self._flag_map.get(flag)
                    if not arg:
                        raise CommandArgumentError(f"Unrecognized option: {flag}")
                    expanded.append(flag)
            else:
                expanded.append(token)
        return expanded

    async def parse_args(
        self, args: list[str] | None = None, from_validate: bool = False
    ) -> dict[str, Any]:
        """Parse Falyx Command arguments."""
        if args is None:
            args = []

        args = self._expand_posix_bundling(args)

        result = {arg.dest: deepcopy(arg.default) for arg in self._arguments}
        positional_args = [arg for arg in self._arguments if arg.positional]
        consumed_positional_indices: set[int] = set()
        consumed_indices: set[int] = set()

        i = 0
        while i < len(args):
            token = args[i]
            if token in self._keyword:
                spec = self._keyword[token]
                action = spec.action

                if action == ArgumentAction.HELP:
                    if not from_validate:
                        self.render_help()
                    raise HelpSignal()
                elif action == ArgumentAction.ACTION:
                    assert isinstance(
                        spec.resolver, BaseAction
                    ), "resolver should be an instance of BaseAction"
                    values, new_i = self._consume_nargs(args, i + 1, spec)
                    try:
                        typed_values = [spec.type(value) for value in values]
                    except ValueError:
                        raise CommandArgumentError(
                            f"Invalid value for '{spec.dest}': expected {spec.type.__name__}"
                        )
                    try:
                        result[spec.dest] = await spec.resolver(*typed_values)
                    except Exception as error:
                        raise CommandArgumentError(
                            f"[{spec.dest}] Action failed: {error}"
                        ) from error
                    consumed_indices.update(range(i, new_i))
                    i = new_i
                elif action == ArgumentAction.STORE_TRUE:
                    result[spec.dest] = True
                    consumed_indices.add(i)
                    i += 1
                elif action == ArgumentAction.STORE_FALSE:
                    result[spec.dest] = False
                    consumed_indices.add(i)
                    i += 1
                elif action == ArgumentAction.COUNT:
                    result[spec.dest] = result.get(spec.dest, 0) + 1
                    consumed_indices.add(i)
                    i += 1
                elif action == ArgumentAction.APPEND:
                    assert result.get(spec.dest) is not None, "dest should not be None"
                    values, new_i = self._consume_nargs(args, i + 1, spec)
                    try:
                        typed_values = [spec.type(value) for value in values]
                    except ValueError:
                        raise CommandArgumentError(
                            f"Invalid value for '{spec.dest}': expected {spec.type.__name__}"
                        )
                    if spec.nargs is None:
                        result[spec.dest].append(spec.type(values[0]))
                    else:
                        result[spec.dest].append(typed_values)
                    consumed_indices.update(range(i, new_i))
                    i = new_i
                elif action == ArgumentAction.EXTEND:
                    assert result.get(spec.dest) is not None, "dest should not be None"
                    values, new_i = self._consume_nargs(args, i + 1, spec)
                    try:
                        typed_values = [spec.type(value) for value in values]
                    except ValueError:
                        raise CommandArgumentError(
                            f"Invalid value for '{spec.dest}': expected {spec.type.__name__}"
                        )
                    result[spec.dest].extend(typed_values)
                    consumed_indices.update(range(i, new_i))
                    i = new_i
                else:
                    values, new_i = self._consume_nargs(args, i + 1, spec)
                    try:
                        typed_values = [spec.type(v) for v in values]
                    except ValueError:
                        raise CommandArgumentError(
                            f"Invalid value for '{spec.dest}': expected {spec.type.__name__}"
                        )
                    if not typed_values and spec.nargs not in ("*", "?"):
                        raise CommandArgumentError(
                            f"Expected at least one value for '{spec.dest}'"
                        )
                    if (
                        spec.nargs in (None, 1, "?")
                        and spec.action != ArgumentAction.APPEND
                    ):
                        result[spec.dest] = (
                            typed_values[0] if len(typed_values) == 1 else typed_values
                        )
                    else:
                        result[spec.dest] = typed_values
                    consumed_indices.update(range(i, new_i))
                    i = new_i
            elif token.startswith("-"):
                # Handle unrecognized option
                raise CommandArgumentError(f"Unrecognized flag: {token}")
            else:
                # Get the next flagged argument index if it exists
                next_flagged_index = -1
                for index, arg in enumerate(args[i:], start=i):
                    if arg.startswith("-"):
                        next_flagged_index = index
                        break
                if next_flagged_index == -1:
                    next_flagged_index = len(args)
                args_consumed = await self._consume_all_positional_args(
                    args[i:next_flagged_index],
                    result,
                    positional_args,
                    consumed_positional_indices,
                )
                i += args_consumed

        # Required validation
        for spec in self._arguments:
            if spec.dest == "help":
                continue
            if spec.required and not result.get(spec.dest):
                raise CommandArgumentError(f"Missing required argument: {spec.dest}")

            if spec.choices and result.get(spec.dest) not in spec.choices:
                raise CommandArgumentError(
                    f"Invalid value for {spec.dest}: must be one of {spec.choices}"
                )

            if spec.action == ArgumentAction.ACTION:
                continue

            if isinstance(spec.nargs, int) and spec.nargs > 1:
                assert isinstance(
                    result.get(spec.dest), list
                ), f"Invalid value for {spec.dest}: expected a list"
                if not result[spec.dest] and not spec.required:
                    continue
                if spec.action == ArgumentAction.APPEND:
                    for group in result[spec.dest]:
                        if len(group) % spec.nargs != 0:
                            raise CommandArgumentError(
                                f"Invalid number of values for {spec.dest}: expected a multiple of {spec.nargs}"
                            )
                elif spec.action == ArgumentAction.EXTEND:
                    if len(result[spec.dest]) % spec.nargs != 0:
                        raise CommandArgumentError(
                            f"Invalid number of values for {spec.dest}: expected a multiple of {spec.nargs}"
                        )
                elif len(result[spec.dest]) != spec.nargs:
                    raise CommandArgumentError(
                        f"Invalid number of values for {spec.dest}: expected {spec.nargs}, got {len(result[spec.dest])}"
                    )

        result.pop("help", None)
        return result

    async def parse_args_split(
        self, args: list[str], from_validate: bool = False
    ) -> tuple[tuple[Any, ...], dict[str, Any]]:
        """
        Returns:
            tuple[args, kwargs] - Positional arguments in defined order,
            followed by keyword argument mapping.
        """
        parsed = await self.parse_args(args, from_validate)
        args_list = []
        kwargs_dict = {}
        for arg in self._arguments:
            if arg.dest == "help":
                continue
            if arg.positional:
                args_list.append(parsed[arg.dest])
            else:
                kwargs_dict[arg.dest] = parsed[arg.dest]
        return tuple(args_list), kwargs_dict

    def get_options_text(self, plain_text=False) -> str:
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
        """Get the usage text for the command."""
        command_keys = self.get_command_keys_text(plain_text)
        options_text = self.get_options_text(plain_text)
        if options_text:
            return f"{command_keys} {options_text}"
        return command_keys

    def render_help(self) -> None:
        usage = self.get_usage()
        self.console.print(f"[bold]usage: {usage}[/bold]\n")

        # Description
        if self.help_text:
            self.console.print(self.help_text + "\n")

        # Arguments
        if self._arguments:
            if self._positional:
                self.console.print("[bold]positional:[/bold]")
                for arg in self._positional.values():
                    flags = arg.get_positional_text()
                    arg_line = Text(f"  {flags:<30} ")
                    help_text = arg.help or ""
                    arg_line.append(help_text)
                    self.console.print(arg_line)
            self.console.print("[bold]options:[/bold]")
            for arg in self._keyword_list:
                flags = ", ".join(arg.flags)
                flags_choice = f"{flags} {arg.get_choice_text()}"
                arg_line = Text(f"  {flags_choice:<30} ")
                help_text = arg.help or ""
                arg_line.append(help_text)
                self.console.print(arg_line)

        # Epilogue
        if self.help_epilogue:
            self.console.print("\n" + self.help_epilogue, style="dim")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CommandArgumentParser):
            return False

        def sorted_args(parser):
            return sorted(parser._arguments, key=lambda a: a.dest)

        return sorted_args(self) == sorted_args(other)

    def __hash__(self) -> int:
        return hash(tuple(sorted(self._arguments, key=lambda a: a.dest)))

    def __str__(self) -> str:
        positional = sum(arg.positional for arg in self._arguments)
        required = sum(arg.required for arg in self._arguments)
        return (
            f"CommandArgumentParser(args={len(self._arguments)}, "
            f"flags={len(self._flag_map)}, keywords={len(self._keyword)}, "
            f"positional={positional}, required={required})"
        )

    def __repr__(self) -> str:
        return str(self)
