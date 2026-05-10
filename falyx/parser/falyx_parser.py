# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from falyx.console import console
from falyx.exceptions import EntryNotFoundError, FalyxOptionError
from falyx.mode import FalyxMode
from falyx.options_manager import OptionsManager
from falyx.parser.parse_result import ParseResult
from falyx.parser.parser_types import (
    FalyxTLDRExample,
    FalyxTLDRInput,
    false_none,
    true_none,
)
from falyx.parser.utils import coerce_value, get_type_name

if TYPE_CHECKING:
    from falyx.falyx import Falyx

builtin_type = type


class OptionAction(Enum):
    STORE = "store"
    STORE_TRUE = "store_true"
    STORE_FALSE = "store_false"
    STORE_BOOL_OPTIONAL = "store_bool_optional"
    COUNT = "count"
    HELP = "help"
    TLDR = "tldr"

    @classmethod
    def choices(cls) -> list[OptionAction]:
        """Return a list of all argument actions."""
        return list(cls)

    @classmethod
    def _get_alias(cls, value: str) -> str:
        aliases = {
            "optional": "store_bool_optional",
            "true": "store_true",
            "false": "store_false",
        }
        return aliases.get(value, value)

    @classmethod
    def _missing_(cls, value: object) -> OptionAction:
        if not isinstance(value, str):
            raise ValueError(f"Invalid {cls.__name__}: {value!r}")
        normalized = value.strip().lower()
        alias = cls._get_alias(normalized)
        for member in cls:
            if member.value == alias:
                return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid {cls.__name__}: '{value}'. Must be one of: {valid}")

    def __str__(self) -> str:
        """Return the string representation of the argument action."""
        return self.value


class OptionScope(Enum):
    ROOT = "root"
    NAMESPACE = "namespace"

    @classmethod
    def _missing_(cls, value: object) -> OptionScope:
        if not isinstance(value, str):
            raise ValueError(f"Invalid {cls.__name__}: {value!r}")
        normalized = value.strip().lower()
        for member in cls:
            if member.value == normalized:
                return member
        valid = ", ".join(member.value for member in cls)
        raise ValueError(f"Invalid {cls.__name__}: '{value}'. Must be one of: {valid}")


@dataclass(slots=True)
class Option:
    flags: tuple[str, ...]
    dest: str
    action: OptionAction = OptionAction.STORE
    type: Any = str
    default: Any = None
    choices: list[str] | None = None
    help: str = ""
    suggestions: list[str] | None = None
    scope: OptionScope = OptionScope.NAMESPACE

    def format_for_help(self) -> str:
        """Return a formatted string of the option's flags for help output."""
        return ", ".join(self.flags)


class FalyxParser:
    RESERVED_DESTS: set[str] = {"help", "tldr"}

    def __init__(self, flx: Falyx) -> None:
        self._flx = flx
        self._options_by_dest: dict[str, Option] = {}
        self._options: list[Option] = []
        self._dest_set: set[str] = set()
        self._tldr_examples: list[FalyxTLDRExample] = []
        self._add_reserved_options()
        self.help_option: Option | None = None
        self.tldr_option: Option | None = None

    def get_flags(self) -> list[str]:
        """Return a list of the first flag for the registered options."""
        return [option.flags[0] for option in self._options]

    def get_options(self) -> list[Option]:
        """Return a list of registered options."""
        return self._options

    def _add_tldr(self):
        """Add TLDR argument to the parser."""
        if "tldr" in self._dest_set:
            return None
        tldr = Option(
            flags=("--tldr", "-T"),
            action=OptionAction.TLDR,
            help="Show quick usage examples.",
            dest="tldr",
            default=False,
        )
        self._register_option(tldr)
        self.tldr_option = tldr

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
        entry, suggestions = self._flx.resolve_entry(entry_key)
        if not entry:
            raise EntryNotFoundError(
                unknown_name=entry_key,
                suggestions=suggestions,
                message_context="TLDR example",
            )
        self._tldr_examples.append(
            FalyxTLDRExample(entry_key=entry_key, usage=usage, description=description)
        )
        self._add_tldr()

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
        for example in examples:
            if isinstance(example, FalyxTLDRExample):
                entry, suggestions = self._flx.resolve_entry(example.entry_key)
                if not entry:
                    raise EntryNotFoundError(
                        unknown_name=example.entry_key,
                        suggestions=suggestions,
                        message_context="TLDR example",
                    )
                self._tldr_examples.append(example)
                self._add_tldr()
            elif len(example) == 3:
                entry_key, usage, description = example
                self.add_tldr_example(
                    entry_key=entry_key,
                    usage=usage,
                    description=description,
                )
                self._add_tldr()
            else:
                raise FalyxOptionError(
                    f"invalid TLDR example format: {example}.\n"
                    "examples must be either FalyxTLDRExample instances "
                    "or tuples of (entry_key, usage, description).",
                )

    def _add_reserved_options(self) -> None:
        help = Option(
            flags=("-h", "--help", "?"),
            dest="help",
            action=OptionAction.HELP,
            help="Show root-level help output and exit.",
            default=False,
        )
        self._register_option(help)
        self.help_option = help

        if not self._flx.disable_verbose_option:
            verbose = Option(
                flags=("-v", "--verbose"),
                dest="verbose",
                action=OptionAction.STORE_TRUE,
                help="Enable verbose logging for the session.",
                default=False,
                scope=OptionScope.ROOT,
            )
            self._register_option(verbose)

        if not self._flx.disable_debug_hooks_option:
            debug_hooks = Option(
                flags=("-d", "--debug-hooks"),
                dest="debug_hooks",
                action=OptionAction.STORE_TRUE,
                help="Log hook execution in detail for the session.",
                default=False,
                scope=OptionScope.ROOT,
            )
            self._register_option(debug_hooks)

        if not self._flx.disable_never_prompt_option:
            never_prompt = Option(
                flags=("-n", "--never-prompt"),
                dest="never_prompt",
                action=OptionAction.STORE_TRUE,
                help="Suppress all prompts for the session.",
                default=False,
                scope=OptionScope.ROOT,
            )
            self._register_option(never_prompt)

    def _register_store_bool_optional(
        self,
        flags: tuple[str, ...],
        dest: str,
        help: str,
    ) -> None:
        """Register a store_bool_optional action with the parser."""
        if len(flags) != 1:
            raise FalyxOptionError(
                "store_bool_optional action can only have a single flag"
            )
        if not flags[0].startswith("--"):
            raise FalyxOptionError(
                "store_bool_optional action must use a long flag (e.g. --flag)"
            )
        base_flag = flags[0]
        negated_flag = f"--no-{base_flag.lstrip('-')}"

        argument = Option(
            flags=flags,
            dest=dest,
            action=OptionAction.STORE_BOOL_OPTIONAL,
            type=true_none,
            default=None,
            help=help,
        )

        negated_argument = Option(
            flags=(negated_flag,),
            dest=dest,
            action=OptionAction.STORE_BOOL_OPTIONAL,
            type=false_none,
            default=None,
            help=help,
        )

        self._register_option(argument)
        self._register_option(negated_argument, bypass_validation=True)

    def _register_option(self, option: Option, bypass_validation: bool = False) -> None:
        self._dest_set.add(option.dest)
        self._options.append(option)
        for flag in option.flags:
            if flag in self._options and not bypass_validation:
                existing = self._options_by_dest[flag]
                raise FalyxOptionError(
                    f"flag '{flag}' is already used by argument '{existing.dest}'"
                )
            self._options_by_dest[flag] = option

    def _validate_flags(self, flags: tuple[str, ...]) -> None:
        if not flags:
            raise FalyxOptionError("no flags provided for option")
        for flag in flags:
            if not isinstance(flag, str):
                raise FalyxOptionError(f"invalid flag '{flag}': must be a string")
            if not flag.startswith("-"):
                raise FalyxOptionError(f"invalid flag '{flag}': must start with '-'")
            if flag.startswith("--") and len(flag) < 3:
                raise FalyxOptionError(
                    f"invalid flag '{flag}': long flags must have at least one character after '--'"
                )
            if flag.startswith("-") and not flag.startswith("--") and len(flag) > 2:
                raise FalyxOptionError(
                    f"invalid flag '{flag}': short flags must be a single character"
                )
            if flag in self._options_by_dest:
                existing = self._options_by_dest[flag]
                raise FalyxOptionError(
                    f"flag '{flag}' is already used by argument '{existing.dest}'"
                )

    def _get_dest_from_flags(self, flags: tuple[str, ...], dest: str | None) -> str:
        if dest:
            if not dest.replace("_", "").isalnum():
                raise FalyxOptionError(
                    f"invalid dest '{dest}': must be a valid identifier (letters, digits, and underscores only)"
                )
            if dest[0].isdigit():
                raise FalyxOptionError(
                    f"invalid dest '{dest}': cannot start with a digit"
                )
            return dest
        dest = None
        for flag in flags:
            cleaned = flag.lstrip("-").replace("-", "_").lower()
            dest = cleaned
            if flag.startswith("--"):
                break
        assert dest is not None, "dest should not be None"
        if not dest.replace("_", "").isalnum():
            raise FalyxOptionError(
                f"invalid dest '{dest}': must be a valid identifier (letters, digits, and underscores only)"
            )
        if dest[0].isdigit():
            raise FalyxOptionError(f"invalid dest '{dest}': cannot start with a digit")
        return dest

    def _validate_action(self, action: str | OptionAction) -> OptionAction:
        if isinstance(action, OptionAction):
            return action
        try:
            return OptionAction(action)
        except ValueError as error:
            raise FalyxOptionError(
                f"invalid option action '{action}' is not a valid OptionAction",
                hint=f"valid actions are: {', '.join(a.value for a in OptionAction)}",
            ) from error

    def _resolve_default(
        self,
        default: Any,
        action: OptionAction,
    ) -> Any:
        if default is None:
            if action == OptionAction.STORE_TRUE:
                return False
            elif action == OptionAction.STORE_FALSE:
                return True
            elif action == OptionAction.STORE_BOOL_OPTIONAL:
                return None
            elif action == OptionAction.COUNT:
                return 0
        elif action is OptionAction.STORE_TRUE and default is not False:
            raise FalyxOptionError(
                f"default value for '{action}' action must be False or None, got {default!r}"
            )
        elif action is OptionAction.STORE_FALSE and default is not True:
            raise FalyxOptionError(
                f"default value for '{action}' action must be True or None, got {default!r}"
            )
        elif action is OptionAction.STORE_BOOL_OPTIONAL:
            raise FalyxOptionError(
                f"default value for '{action}' action must be None, got {default!r}"
            )
        elif action in (OptionAction.HELP, OptionAction.TLDR, OptionAction.COUNT):
            raise FalyxOptionError(f"default value cannot be set for action '{action}'.")
        return default

    def _validate_default_type(
        self,
        default: Any,
        expected_type: Any,
        dest: str,
    ) -> None:
        if default is None:
            return None
        try:
            coerce_value(default, expected_type)
        except Exception as error:
            type_name = get_type_name(expected_type)
            raise FalyxOptionError(
                f"invalid default value {default!r} for '{dest}' cannot be coerced to {type_name} error: {error}"
            ) from error

    def _normalize_choices(
        self,
        choices: list[str] | None,
        expected_type: type,
        action: OptionAction,
    ) -> list[Any]:
        if choices is None:
            choices = []
        else:
            if action in (
                OptionAction.STORE_TRUE,
                OptionAction.STORE_FALSE,
                OptionAction.STORE_BOOL_OPTIONAL,
            ):
                raise FalyxOptionError(
                    f"choices cannot be specified for '{action}' actions"
                )
            if isinstance(choices, dict):
                raise FalyxOptionError("choices cannot be a dict")
            try:
                choices = list(choices)
            except TypeError as error:
                raise FalyxOptionError(
                    "choices must be iterable (like list, tuple, or set)"
                ) from error
        for choice in choices:
            try:
                coerce_value(choice, expected_type)
            except Exception as error:
                type_name = get_type_name(expected_type)
                raise FalyxOptionError(
                    f"invalid choice {choice!r} cannot be coerced to {type_name} error: {error}"
                ) from error
        return choices

    def add_option(
        self,
        flags: tuple[str, ...],
        dest: str,
        action: str | OptionAction = "store",
        type: type = str,
        default: Any = None,
        choices: list[str] | None = None,
        help: str = "",
        suggestions: list[str] | None = None,
    ) -> None:
        self._validate_flags(flags)
        dest = self._get_dest_from_flags(flags, dest)
        if dest in self.RESERVED_DESTS:
            raise FalyxOptionError(
                f"invalid dest '{dest}': '{dest}' is reserved and cannot be used as an option dest"
            )
        if dest in self._dest_set:
            raise FalyxOptionError(f"duplicate option dest '{dest}'")
        action = self._validate_action(action)
        default = self._resolve_default(default, action)
        self._validate_default_type(default, type, dest)
        choices = self._normalize_choices(choices, type, action)
        if default is not None and choices and default not in choices:
            choices_str = ", ".join((str(choice) for choice in choices))
            raise FalyxOptionError(
                f"default value {default!r} is not in allowed choices: {choices_str}"
            )
        if suggestions is not None and not isinstance(suggestions, list):
            type_name = get_type_name(suggestions)
            raise FalyxOptionError(f"suggestions must be a list or None, got {type_name}")
        if isinstance(suggestions, list) and not all(
            isinstance(suggestion, str) for suggestion in suggestions
        ):
            raise FalyxOptionError("suggestions must be a list of strings")
        if action is OptionAction.STORE_BOOL_OPTIONAL:
            self._register_store_bool_optional(flags, dest, help)
            return None
        option = Option(
            flags=flags,
            dest=dest,
            action=action,
            type=type,
            default=default,
            choices=choices,
            help=help,
            suggestions=suggestions,
        )
        self._register_option(option)

    def apply_to_options(
        self,
        parse_result: ParseResult,
        options: OptionsManager,
    ) -> None:
        for dest, value in parse_result.options.items():
            options.set(dest, value, namespace_name=self_flx.namespace_name)
        for dest, value in parse_result.root_options.items():
            options.set(dest, value, namespace_name="root")

    def _can_bundle_option(self, option: Option) -> bool:
        return option.action in {
            OptionAction.STORE_TRUE,
            OptionAction.STORE_FALSE,
            OptionAction.COUNT,
            OptionAction.HELP,
            OptionAction.TLDR,
        }

    def _resolve_posix_bundling(self, tokens: list[str]) -> list[str]:
        """Expand POSIX-style bundled arguments into separate arguments."""
        expanded: list[str] = []
        for token in tokens:
            if not token.startswith("-") or token.startswith("--") or len(token) <= 2:
                expanded.append(token)
                continue

            bundle = [f"-{char}" for char in token[1:]]

            if (
                all(
                    flag in self._options_by_dest
                    and self._can_bundle_option(self._options_by_dest[flag])
                    for flag in bundle[:-1]
                )
                and bundle[-1] in self._options_by_dest
            ):
                expanded.extend(bundle)
            else:
                expanded.append(token)
        return expanded

    def _default_values(self) -> tuple[dict[str, Any], dict[str, Any]]:
        values: dict[str, Any] = {}
        root_values: dict[str, Any] = {}

        for option in self._options:
            if option.scope == OptionScope.ROOT:
                root_values[option.dest] = option.default
            elif option.scope == OptionScope.NAMESPACE:
                values.setdefault(option.dest, option.default)
            else:
                assert False, f"unhandled option scope: {option.scope}"

        return values, root_values

    def _consume_option(
        self,
        option: Option,
        argv: list[str],
        index: int,
        values: dict[str, Any],
    ) -> int:
        match option.action:
            case OptionAction.STORE_TRUE:
                values[option.dest] = True
                return index + 1

            case OptionAction.STORE_FALSE:
                values[option.dest] = False
                return index + 1

            case OptionAction.STORE_BOOL_OPTIONAL:
                values[option.dest] = option.type(None)
                return index + 1

            case OptionAction.COUNT:
                values[option.dest] = int(values.get(option.dest) or 0) + 1
                return index + 1

            case OptionAction.HELP:
                values[option.dest] = True
                return index + 1

            case OptionAction.TLDR:
                values[option.dest] = True
                return index + 1

            case OptionAction.STORE:
                value_index = index + 1
                if value_index >= len(argv):
                    raise FalyxOptionError(f"option '{argv[index]}' expected a value")

                raw_value = argv[value_index]
                try:
                    value = coerce_value(raw_value, option.type)
                except Exception as error:
                    raise FalyxOptionError(
                        f"invalid value for '{argv[index]}': {error}"
                    ) from error

                if option.choices and value not in option.choices:
                    choices = ", ".join(str(choice) for choice in option.choices)
                    raise FalyxOptionError(
                        f"invalid value for '{argv[index]}': expected one of {{{choices}}}"
                    )

                values[option.dest] = value
                return index + 2

        raise FalyxOptionError(f"unsupported option action: {option.action}")

    def parse_args(
        self,
        argv: list[str] | None = None,
    ) -> ParseResult:
        raw_argv = argv or []
        arguments = self._resolve_posix_bundling(raw_argv)
        values, root_values = self._default_values()

        index = 0
        while index < len(arguments):
            token = arguments[index]

            # Explicit option terminator. Everything after belongs to routing/command.
            if token == "--":
                index += 1
                break

            # First non-option is the route boundary.
            if not token.startswith("-"):
                break

            # Unknown leading option is an error at this scope.
            # This is what keeps root/namespace options honest.
            option = self._options_by_dest.get(token)
            if option is None:
                raise FalyxOptionError(
                    f"unknown option '{token}' for '{self._flx.program or self._flx.title}'"
                )

            target_values = root_values if option.scope == OptionScope.ROOT else values
            index = self._consume_option(option, arguments, index, target_values)

        remaining_argv = arguments[index:]

        help_requested = values.get("help", False) or values.get("tldr", False)

        return ParseResult(
            mode=FalyxMode.HELP if help_requested else FalyxMode.COMMAND,
            raw_argv=raw_argv,
            options=values,
            root_options=root_values,
            remaining_argv=remaining_argv,
            help=values.get("help", False),
            tldr=values.get("tldr", False),
            current_head=remaining_argv[0] if remaining_argv else "",
        )
