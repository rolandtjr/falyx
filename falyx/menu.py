from __future__ import annotations

from dataclasses import dataclass

from falyx.action import BaseAction
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


class MenuOptionMap(CaseInsensitiveDict):
    """
    Manages menu options including validation, reserved key protection,
    and special signal entries like Quit and Back.
    """

    RESERVED_KEYS = {"Q", "B"}

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
            "Q",
            MenuOption("Exit", SignalAction("Quit", QuitSignal()), OneColors.DARK_RED),
        )
        self._add_reserved(
            "B",
            MenuOption("Back", SignalAction("Back", BackSignal()), OneColors.DARK_YELLOW),
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

    def items(self, include_reserved: bool = True):
        for k, v in super().items():
            if not include_reserved and k in self.RESERVED_KEYS:
                continue
            yield k, v
