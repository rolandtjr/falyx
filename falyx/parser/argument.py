# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""argument.py"""
from dataclasses import dataclass
from typing import Any

from falyx.action.base_action import BaseAction
from falyx.parser.argument_action import ArgumentAction


@dataclass
class Argument:
    """
    Represents a command-line argument.

    Attributes:
        flags (tuple[str, ...]): Short and long flags for the argument.
        dest (str): The destination name for the argument.
        action (ArgumentAction): The action to be taken when the argument is encountered.
        type (Any): The type of the argument (e.g., str, int, float) or a callable that converts the argument value.
        default (Any): The default value if the argument is not provided.
        choices (list[str] | None): A list of valid choices for the argument.
        required (bool): True if the argument is required, False otherwise.
        help (str): Help text for the argument.
        nargs (int | str | None): Number of arguments expected. Can be an int, '?', '*', '+', or None.
        positional (bool): True if the argument is positional (no leading - or -- in flags), False otherwise.
        resolver (BaseAction | None):
            An action object that resolves the argument, if applicable.
        lazy_resolver (bool): True if the resolver should be called lazily, False otherwise
        suggestions (list[str] | None): A list of suggestions for the argument.
    """

    flags: tuple[str, ...]
    dest: str
    action: ArgumentAction = ArgumentAction.STORE
    type: Any = str
    default: Any = None
    choices: list[str] | None = None
    required: bool = False
    help: str = ""
    nargs: int | str | None = None
    positional: bool = False
    resolver: BaseAction | None = None
    lazy_resolver: bool = False
    suggestions: list[str] | None = None

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
                ArgumentAction.ACTION,
            )
            and not self.positional
        ):
            choice_text = self.dest.upper()
        elif self.action in (
            ArgumentAction.STORE,
            ArgumentAction.APPEND,
            ArgumentAction.EXTEND,
            ArgumentAction.ACTION,
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
