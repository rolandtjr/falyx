"""bottom_bar.py"""
from typing import Any, Callable, Optional

from prompt_toolkit.formatted_text import HTML, merge_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console

from falyx.themes.colors import OneColors
from falyx.utils import CaseInsensitiveDict


class BottomBar:
    """Bottom Bar class for displaying a bottom bar in the terminal."""
    def __init__(self, columns: int = 3, key_bindings: KeyBindings | None = None):
        self.columns = columns
        self.console = Console()
        self._items: list[Callable[[], HTML]] = []
        self._named_items: dict[str, Callable[[], HTML]] = {}
        self._states: dict[str, Any] = CaseInsensitiveDict()
        self.toggles: list[str] = []
        self.key_bindings = key_bindings or KeyBindings()

    def get_space(self) -> int:
        return self.console.width // self.columns

    def add_static(
        self, name: str, text: str, fg: str = OneColors.BLACK, bg: str = OneColors.WHITE
    ) -> None:
        def render():
            return HTML(
                f"<style fg='{fg}' bg='{bg}'>{text:^{self.get_space()}}</style>"
            )

        self._add_named(name, render)

    def add_counter(
        self,
        name: str,
        label: str,
        current: int,
        fg: str = OneColors.BLACK,
        bg: str = OneColors.WHITE,
    ) -> None:
        self._states[name] = (label, current)

        def render():
            label_, current_ = self._states[name]
            text = f"{label_}: {current_}"
            return HTML(
                f"<style fg='{fg}' bg='{bg}'>{text:^{self.get_space()}}</style>"
            )

        self._add_named(name, render)

    def add_total_counter(
        self,
        name: str,
        label: str,
        current: int,
        total: int,
        fg: str = OneColors.BLACK,
        bg: str = OneColors.WHITE,
    ) -> None:
        self._states[name] = (label, current, total)

        if current > total:
            raise ValueError(
                f"Current value {current} is greater than total value {total}"
            )

        def render():
            label_, current_, text_ = self._states[name]
            text = f"{label_}: {current_}/{text_}"
            return HTML(
                f"<style fg='{fg}' bg='{bg}'>{text:^{self.get_space()}}</style>"
            )

        self._add_named(name, render)

    def add_toggle(
        self,
        key: str,
        label: str,
        state: bool,
        fg: str = OneColors.BLACK,
        bg_on: str = OneColors.GREEN,
        bg_off: str = OneColors.DARK_RED,
    ) -> None:
        key = key.upper()
        if key in self.toggles:
            raise ValueError(f"Key {key} is already used as a toggle")
        self._states[key] = (label, state)
        self.toggles.append(key)

        def render():
            label_, state_ = self._states[key]
            color = bg_on if state_ else bg_off
            status = "ON" if state_ else "OFF"
            text = f"({key.upper()}) {label_}: {status}"
            return HTML(
                f"<style bg='{color}' fg='{fg}'>{text:^{self.get_space()}}</style>"
            )

        self._add_named(key, render)

        for k in (key.upper(), key.lower()):

            @self.key_bindings.add(k)
            def _(event, key=k):
                self.toggle_state(key)

    def toggle_state(self, name: str) -> bool:
        label, state = self._states.get(name, (None, False))
        new_state = not state
        self.update_toggle(name, new_state)
        return new_state

    def update_toggle(self, name: str, state: bool) -> None:
        if name in self._states:
            label, _ = self._states[name]
            self._states[name] = (label, state)

    def increment_counter(self, name: str) -> None:
        if name in self._states:
            label, current = self._states[name]
            self._states[name] = (label, current + 1)

    def increment_total_counter(self, name: str) -> None:
        if name in self._states:
            label, current, total = self._states[name]
            if current < total:
                self._states[name] = (label, current + 1, total)

    def update_counter(
        self, name: str, current: Optional[int] = None, total: Optional[int] = None
    ) -> None:
        if name in self._states:
            label, c, t = self._states[name]
            self._states[name] = (
                label,
                current if current is not None else c,
                total if total is not None else t,
            )

    def _add_named(self, name: str, render_fn: Callable[[], HTML]) -> None:
        self._named_items[name] = render_fn
        self._items = list(self._named_items.values())

    def render(self):
        return merge_formatted_text([fn() for fn in self._items])
