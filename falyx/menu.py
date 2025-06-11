from __future__ import annotations

from dataclasses import dataclass

from prompt_toolkit.formatted_text import FormattedText

from falyx.action.base_action import BaseAction
from falyx.signals import BackSignal, QuitSignal
from falyx.themes import OneColors
from falyx.utils import CaseInsensitiveDict


@dataclass
class MenuOption:
    """Represents a single menu option with a description and an action to execute."""

    description: str
    action: BaseAction
    style: str = OneColors.WHITE

    def __post_init__(self):
        if not isinstance(self.description, str):
            raise TypeError("MenuOption description must be a string.")
        if not isinstance(self.action, BaseAction):
            raise TypeError("MenuOption action must be a BaseAction instance.")

    def render(self, key: str) -> str:
        """Render the menu option for display."""
        return f"[{OneColors.WHITE}][{key}][/] [{self.style}]{self.description}[/]"

    def render_prompt(self, key: str) -> FormattedText:
        """Render the menu option for prompt display."""
        return FormattedText(
            [(OneColors.WHITE, f"[{key}] "), (self.style, self.description)]
        )


class MenuOptionMap(CaseInsensitiveDict):
    """
    Manages menu options including validation, reserved key protection,
    and special signal entries like Quit and Back.
    """

    RESERVED_KEYS = {"B", "X"}

    def __init__(
        self,
        options: dict[str, MenuOption] | None = None,
        allow_reserved: bool = False,
    ):
        super().__init__()
        self.allow_reserved = allow_reserved
        if options:
            self.update(options)
        self._inject_reserved_defaults()

    def _inject_reserved_defaults(self):
        from falyx.action import SignalAction

        self._add_reserved(
            "B",
            MenuOption("Back", SignalAction("Back", BackSignal()), OneColors.DARK_YELLOW),
        )
        self._add_reserved(
            "X",
            MenuOption("Exit", SignalAction("Quit", QuitSignal()), OneColors.DARK_RED),
        )

    def _add_reserved(self, key: str, option: MenuOption) -> None:
        """Add a reserved key, bypassing validation."""
        norm_key = key.upper()
        super().__setitem__(norm_key, option)

    def __setitem__(self, key: str, option: MenuOption) -> None:
        if not isinstance(option, MenuOption):
            raise TypeError(f"Value for key '{key}' must be a MenuOption.")
        norm_key = key.upper()
        if norm_key in self.RESERVED_KEYS and not self.allow_reserved:
            raise ValueError(
                f"Key '{key}' is reserved and cannot be used in MenuOptionMap."
            )
        super().__setitem__(norm_key, option)

    def __delitem__(self, key: str) -> None:
        if key.upper() in self.RESERVED_KEYS and not self.allow_reserved:
            raise ValueError(f"Cannot delete reserved option '{key}'.")
        super().__delitem__(key)

    def update(self, other=None, **kwargs):
        """Update the selection options with another dictionary."""
        if other:
            for key, option in other.items():
                if not isinstance(option, MenuOption):
                    raise TypeError(f"Value for key '{key}' must be a SelectionOption.")
                self[key] = option
        for key, option in kwargs.items():
            if not isinstance(option, MenuOption):
                raise TypeError(f"Value for key '{key}' must be a SelectionOption.")
            self[key] = option

    def items(self, include_reserved: bool = True):
        for key, option in super().items():
            if not include_reserved and key in self.RESERVED_KEYS:
                continue
            yield key, option
