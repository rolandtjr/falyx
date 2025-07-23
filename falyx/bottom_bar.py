# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Provides the `BottomBar` class for managing a customizable bottom status bar in
Falyx-based CLI applications.

The bottom bar is rendered using `prompt_toolkit` and supports:
- Rich-formatted static content
- Live-updating value trackers and counters
- Toggle switches activated via Ctrl+<key> bindings
- Config-driven visual and behavioral controls

Each item in the bar is registered by name and rendered in columns across the
bottom of the terminal. Toggles are linked to user-defined state accessors and
mutators, and can be automatically bound to `OptionsManager` values for full
integration with Falyx CLI argument parsing.

Key Features:
- Live rendering of structured status items using Rich-style HTML
- Custom or built-in item types: static text, dynamic counters, toggles, value displays
- Ctrl+key toggle handling via `prompt_toolkit.KeyBindings`
- Columnar layout with automatic width scaling
- Optional integration with `OptionsManager` for dynamic state toggling

Usage Example:
    bar = BottomBar(columns=3)
    bar.add_static("env", "ENV: dev")
    bar.add_toggle("d", "Debug", get_debug, toggle_debug)
    bar.add_value_tracker("attempts", "Retries", get_retry_count)
    bar.render()

Used by Falyx to provide a persistent UI element showing toggles, system state,
and runtime telemetry below the input prompt.
"""

from typing import Any, Callable

from prompt_toolkit.formatted_text import HTML, merge_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from rich.console import Console

from falyx.console import console
from falyx.options_manager import OptionsManager
from falyx.themes import OneColors
from falyx.utils import CaseInsensitiveDict, chunks


class BottomBar:
    """
    Bottom Bar class for displaying a bottom bar in the terminal.

    Args:
        columns (int): Number of columns in the bottom bar.
        key_bindings (KeyBindings, optional): Key bindings for the bottom bar.
        key_validator (Callable[[str], bool], optional): Function to validate toggle keys.
            Must return True if key is available, otherwise False.
    """

    RESERVED_CTRL_KEYS = {"c", "d", "z", "v"}

    def __init__(
        self,
        columns: int = 3,
        key_bindings: KeyBindings | None = None,
    ) -> None:
        self.columns = columns
        self.console: Console = console
        self._named_items: dict[str, Callable[[], HTML]] = {}
        self._value_getters: dict[str, Callable[[], Any]] = CaseInsensitiveDict()
        self.toggle_keys: list[str] = []
        self.key_bindings = key_bindings or KeyBindings()

    @staticmethod
    def default_render(label: str, value: Any, fg: str, bg: str, width: int) -> HTML:
        return HTML(f"<style fg='{fg}' bg='{bg}'>{label}: {value:^{width}}</style>")

    @property
    def space(self) -> int:
        return self.console.width // self.columns

    def add_custom(self, name: str, render_fn: Callable[[], HTML]) -> None:
        """Add a custom render function to the bottom bar."""
        if not callable(render_fn):
            raise ValueError("`render_fn` must be callable")
        self._add_named(name, render_fn)

    def add_static(
        self,
        name: str,
        text: str,
        fg: str = OneColors.BLACK,
        bg: str = OneColors.WHITE,
    ) -> None:
        def render():
            return HTML(f"<style fg='{fg}' bg='{bg}'>{text:^{self.space}}</style>")

        self._add_named(name, render)

    def add_value_tracker(
        self,
        name: str,
        label: str,
        get_value: Callable[[], Any],
        fg: str = OneColors.BLACK,
        bg: str = OneColors.WHITE,
    ) -> None:
        if not callable(get_value):
            raise ValueError("`get_value` must be a callable returning any value")
        self._value_getters[name] = get_value

        def render():
            get_value_ = self._value_getters[name]
            current_ = get_value_()
            text = f"{label}: {current_}"
            return HTML(f"<style fg='{fg}' bg='{bg}'>{text:^{self.space}}</style>")

        self._add_named(name, render)

    def add_total_counter(
        self,
        name: str,
        label: str,
        get_current: Callable[[], int],
        total: int,
        fg: str = OneColors.BLACK,
        bg: str = OneColors.WHITE,
        enforce_total: bool = True,
    ) -> None:
        if not callable(get_current):
            raise ValueError("`get_current` must be a callable returning int")

        self._value_getters[name] = get_current

        def render():
            get_current_ = self._value_getters[name]
            current_value = get_current_()
            if current_value > total and enforce_total:
                raise ValueError(
                    f"Current value {current_value} is greater than total value {total}"
                )
            text = f"{label}: {current_value}/{total}"
            return HTML(f"<style fg='{fg}' bg='{bg}'>{text:^{self.space}}</style>")

        self._add_named(name, render)

    def add_toggle(
        self,
        key: str,
        label: str,
        get_state: Callable[[], bool],
        toggle_state: Callable[[], None],
        fg: str = OneColors.BLACK,
        bg_on: str = OneColors.GREEN,
        bg_off: str = OneColors.DARK_RED,
    ) -> None:
        """
        Add a toggle to the bottom bar.
        Always uses the ctrl + key combination for toggling.

        Args:
            key (str): The key to toggle the state.
            label (str): The label for the toggle.
            get_state (Callable[[], bool]): Function to get the current state.
            toggle_state (Callable[[], None]): Function to toggle the state.
            fg (str): Foreground color for the label.
            bg_on (str): Background color when the toggle is ON.
            bg_off (str): Background color when the toggle is OFF.
        """
        key = key.lower()
        if key in self.RESERVED_CTRL_KEYS:
            raise ValueError(
                f"'{key}' is a reserved terminal control key and cannot be used for toggles."
            )
        if not callable(get_state):
            raise ValueError("`get_state` must be a callable returning bool")
        if not callable(toggle_state):
            raise ValueError("`toggle_state` must be a callable")
        if key in self.toggle_keys:
            raise ValueError(f"Key {key} is already used as a toggle")

        self._value_getters[key] = get_state
        self.toggle_keys.append(key)

        def render():
            get_state_ = self._value_getters[key]
            color = bg_on if get_state_() else bg_off
            status = "ON" if get_state_() else "OFF"
            text = f"(^{key.lower()}) {label}: {status}"
            return HTML(f"<style bg='{color}' fg='{fg}'>{text:^{self.space}}</style>")

        self._add_named(key, render)

        @self.key_bindings.add(f"c-{key.lower()}", eager=True)
        def _(_: KeyPressEvent):
            toggle_state()

    def add_toggle_from_option(
        self,
        key: str,
        label: str,
        options: OptionsManager,
        option_name: str,
        namespace_name: str = "cli_args",
        fg: str = OneColors.BLACK,
        bg_on: str = OneColors.GREEN,
        bg_off: str = OneColors.DARK_RED,
    ) -> None:
        """Add a toggle to the bottom bar based on an option from OptionsManager."""
        self.add_toggle(
            key=key,
            label=label,
            get_state=options.get_value_getter(option_name, namespace_name),
            toggle_state=options.get_toggle_function(option_name, namespace_name),
            fg=fg,
            bg_on=bg_on,
            bg_off=bg_off,
        )

    @property
    def values(self) -> dict[str, Any]:
        """Return the current computed values for all registered items."""
        return {label: getter() for label, getter in self._value_getters.items()}

    def get_value(self, name: str) -> Any:
        """Get the current value of a registered item."""
        if name not in self._value_getters:
            raise ValueError(f"No value getter registered under name: '{name}'")
        return self._value_getters[name]()

    def remove_item(self, name: str) -> None:
        """Remove an item from the bottom bar."""
        self._named_items.pop(name, None)
        self._value_getters.pop(name, None)
        if name in self.toggle_keys:
            self.toggle_keys.remove(name)

    def clear(self) -> None:
        """Clear all items from the bottom bar."""
        self._value_getters.clear()
        self._named_items.clear()
        self.toggle_keys.clear()

    def _add_named(self, name: str, render_fn: Callable[[], HTML]) -> None:
        if name in self._named_items:
            raise ValueError(f"Bottom bar item '{name}' already exists")
        self._named_items[name] = render_fn

    def render(self):
        """Render the bottom bar."""
        lines = []
        for chunk in chunks(self._named_items.values(), self.columns):
            lines.extend(list(chunk))
            lines.append(lambda: HTML("\n"))
        return merge_formatted_text([fn() for fn in lines[:-1]])
