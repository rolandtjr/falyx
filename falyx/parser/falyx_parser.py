# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from falyx.exceptions import EntryNotFoundError, FalyxOptionError
from falyx.mode import FalyxMode
from falyx.parser.option import Option, OptionScope
from falyx.parser.option_action import OptionAction
from falyx.parser.parse_result import ParseResult
from falyx.parser.parser_types import (
    FalyxTLDRExample,
    FalyxTLDRInput,
    OptionState,
    false_none,
    true_none,
)
from falyx.parser.utils import coerce_value, get_type_name

if TYPE_CHECKING:
    from falyx.falyx import Falyx

builtin_type = type


class FalyxParser:
    RESERVED_DESTS: set[str] = {"help", "tldr"}

    def __init__(self, flx: Falyx) -> None:
        self._flx = flx
        self._options_by_dest: dict[str, Option] = {}
        self._options: list[Option] = []
        self._dest_set: set[str] = set()
        self._tldr_examples: list[FalyxTLDRExample] = []
        self.help_option: Option | None = None
        self.tldr_option: Option | None = None
        self._last_option_states: dict[str, OptionState] = {}
        self._add_reserved_options()

    def get_flags(self) -> list[str]:
        """Return a list of the first flag for the registered options."""
        return [option.flags[0] for option in self._options]

    def get_options(self) -> list[Option]:
        """Return a list of registered options."""
        return self._options

    def _add_tldr(self):
        """Add TLDR option to the parser."""
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
            flags=("-h", "--help"),
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
    ) -> Option:
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

        option = Option(
            flags=flags,
            dest=dest,
            action=OptionAction.STORE_BOOL_OPTIONAL,
            type=true_none,
            default=None,
            help=help,
        )

        negated_option = Option(
            flags=(negated_flag,),
            dest=dest,
            action=OptionAction.STORE_BOOL_OPTIONAL,
            type=false_none,
            default=None,
            help=help,
        )

        self._register_option(option)
        self._register_option(negated_option, bypass_validation=True)
        return option

    def _register_option(self, option: Option, bypass_validation: bool = False) -> None:
        self._dest_set.add(option.dest)
        self._options.append(option)
        self._last_option_states[option.dest] = OptionState(option)
        for flag in option.flags:
            if flag in self._options_by_dest and not bypass_validation:
                existing = self._options_by_dest[flag]
                raise FalyxOptionError(
                    f"flag '{flag}' is already used by option '{existing.dest}'"
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
                    f"flag '{flag}' is already used by option '{existing.dest}'"
                )
            if not re.match(r"^[a-zA-Z0-9_-]+$", flag.lstrip("-")):
                raise FalyxOptionError(
                    f"invalid flag '{flag}': must only contain letters, digits, underscores, or hyphens"
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

    def _normalize_default_type(
        self,
        default: Any,
        expected_type: Any,
        dest: str,
    ) -> Any:
        if default is None:
            return None
        try:
            return coerce_value(default, expected_type)
        except Exception as error:
            type_name = get_type_name(expected_type)
            raise FalyxOptionError(
                f"invalid default value {default!r} for '{dest}' cannot be coerced to {type_name} error: {error}"
            ) from error

    def _normalize_choices(
        self,
        choices: list[str] | None,
        expected_type: Callable[[Any], Any],
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
        normalized: list[Any] = []
        for choice in choices:
            try:
                normalized.append(coerce_value(choice, expected_type))
            except Exception as error:
                type_name = get_type_name(expected_type)
                raise FalyxOptionError(
                    f"invalid choice {choice!r} cannot be coerced to {type_name} error: {error}"
                ) from error
        return normalized

    def add_option(
        self,
        *flags: str,
        action: str | OptionAction = "store",
        default: Any = None,
        type: Callable[[Any], Any] = str,
        choices: list[str] | None = None,
        help: str = "",
        dest: str | None = None,
        suggestions: list[str] | None = None,
    ) -> Option:
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

        if action is OptionAction.STORE:
            default = self._normalize_default_type(default, type, dest)

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
            return self._register_store_bool_optional(flags, dest, help)
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
        return option

    def _filter_suggestions(
        self,
        suggestion: str,
        prefix: str,
        cursor_at_end_of_token: bool,
    ) -> bool:
        if cursor_at_end_of_token:
            return True
        return suggestion.startswith(prefix)

    def _value_suggestions_for_option(
        self,
        option: Option,
        prefix: str,
        cursor_at_end_of_token: bool,
    ) -> list[str]:
        if option.choices:
            return [
                str(choice)
                for choice in option.choices
                if self._filter_suggestions(str(choice), prefix, cursor_at_end_of_token)
            ]
        if option.suggestions:
            return [
                suggestion
                for suggestion in option.suggestions
                if self._filter_suggestions(suggestion, prefix, cursor_at_end_of_token)
            ]
        return []

    def suggest_next(
        self,
        args: list[str],
        cursor_at_end_of_token: bool,
    ) -> tuple[list[str], bool]:
        """Suggest the next possible flags based on the current input stub."""
        expecting_value = False
        if not args:
            return [], expecting_value
        options = self._resolve_posix_bundling(args)
        consumed_dests = [
            state.option.dest
            for state in self._last_option_states.values()
            if state.consumed
        ]

        remaining_flags = [
            flag
            for flag, option in self._options_by_dest.items()
            if option.dest not in consumed_dests
        ]

        last = options[-1] if options else ""

        last_option_in_options = None
        for option in reversed(options):
            if option in self._options_by_dest:
                last_option_in_options = self._options_by_dest[option]
                break

        suggestions: list[str] = []
        if last.startswith("-") and last not in self._options_by_dest:
            suggestions.extend(flag for flag in remaining_flags if flag.startswith(last))
        elif (
            last_option_in_options
            and not self._last_option_states[last_option_in_options.dest].consumed
        ):
            suggestions.extend(
                self._value_suggestions_for_option(
                    last_option_in_options,
                    prefix=last,
                    cursor_at_end_of_token=cursor_at_end_of_token,
                )
            )
            if last_option_in_options.action is OptionAction.STORE:
                expecting_value = True

        return suggestions, expecting_value

    def _can_bundle_option(self, option: Option) -> bool:
        return option.action in {
            OptionAction.STORE_TRUE,
            OptionAction.STORE_FALSE,
            OptionAction.COUNT,
            OptionAction.HELP,
            OptionAction.TLDR,
        }

    def _resolve_posix_bundling(self, tokens: list[str]) -> list[str]:
        """Expand POSIX-style bundled options into separate options."""
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
        option_states: dict[str, OptionState],
    ) -> int:
        match option.action:
            case OptionAction.STORE_TRUE:
                values[option.dest] = True
                option_states[option.dest].set_consumed()
                return index + 1

            case OptionAction.STORE_FALSE:
                values[option.dest] = False
                option_states[option.dest].set_consumed()
                return index + 1

            case OptionAction.STORE_BOOL_OPTIONAL:
                values[option.dest] = option.type(True)
                option_states[option.dest].set_consumed()
                return index + 1

            case OptionAction.COUNT:
                values[option.dest] = int(values.get(option.dest) or 0) + 1
                option_states[option.dest].set_consumed()
                return index + 1

            case OptionAction.HELP:
                values[option.dest] = True
                option_states[option.dest].set_consumed()
                return index + 1

            case OptionAction.TLDR:
                values[option.dest] = True
                option_states[option.dest].set_consumed()
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
                option_states[option.dest].set_consumed()
                return index + 2

        raise FalyxOptionError(f"unsupported option action: {option.action}")

    def parse_args(
        self,
        argv: list[str] | None = None,
    ) -> ParseResult:
        option_states = {option.dest: OptionState(option) for option in self._options}
        self._last_option_states = option_states
        raw_argv = argv or []
        arguments = self._resolve_posix_bundling(raw_argv)
        root_options: dict[str, Any] = {}
        namespace_options: dict[str, Any] = {}

        index = 0
        while index < len(arguments):
            token = arguments[index]

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

            target_values = (
                root_options if option.scope == OptionScope.ROOT else namespace_options
            )
            index = self._consume_option(
                option,
                arguments,
                index,
                target_values,
                option_states,
            )

        remaining_argv = arguments[index:]

        help_requested = namespace_options.get("help", False) or namespace_options.get(
            "tldr", False
        )

        namespace_defaults, root_defaults = self._default_values()
        return ParseResult(
            mode=FalyxMode.HELP if help_requested else FalyxMode.COMMAND,
            raw_argv=raw_argv,
            root_defaults=root_defaults,
            root_options=root_options,
            namespace_defaults=namespace_defaults,
            namespace_options=namespace_options,
            remaining_argv=remaining_argv,
            help=namespace_options.get("help", False),
            tldr=namespace_options.get("tldr", False),
            current_head=remaining_argv[0] if remaining_argv else "",
        )
