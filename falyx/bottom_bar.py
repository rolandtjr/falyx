"""bottom_bar.py"""

from typing import Any, Callable

from prompt_toolkit.formatted_text import HTML, merge_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console

from falyx.options_manager import OptionsManager
from falyx.themes.colors import OneColors
from falyx.utils import CaseInsensitiveDict


class BottomBar:
    """
    Bottom Bar class for displaying a bottom bar in the terminal.

    Args:
        columns (int): Number of columns in the bottom bar.
        key_bindings (KeyBindings, optional): Key bindings for the bottom bar.
        key_validator (Callable[[str], bool], optional): Function to validate toggle keys.
            Must return True if key is available, otherwise False.
    """

    def __init__(
        self,
        columns: int = 3,
        key_bindings: KeyBindings | None = None,
        key_validator: Callable[[str], bool] | None = None,
    ) -> None:
        self.columns = columns
        self.console = Console()
        self._items: list[Callable[[], HTML]] = []
        self._named_items: dict[str, Callable[[], HTML]] = {}
        self._value_getters: dict[str, Callable[[], Any]] = CaseInsensitiveDict()
        self.toggle_keys: list[str] = []
        self.key_bindings = key_bindings or KeyBindings()
        self.key_validator = key_validator

    @staticmethod
    def default_render(label: str, value: Any, fg: str, bg: str, width: int) -> HTML:
        return HTML(f"<style fg='{fg}' bg='{bg}'>{label}: {value:^{width}}</style>")

    @property
    def space(self) -> int:
        return self.console.width // self.columns

    def add_custom(
        self,
        name: str,
        render_fn: Callable[[], HTML]
    ) -> None:
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
            return HTML(
                f"<style fg='{fg}' bg='{bg}'>{text:^{self.space}}</style>"
            )

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
            return HTML(
                f"<style fg='{fg}' bg='{bg}'>{text:^{self.space}}</style>"
            )

        self._add_named(name, render)

    def add_total_counter(
        self,
        name: str,
        label: str,
        get_current: Callable[[], int],
        total: int,
        fg: str = OneColors.BLACK,
        bg: str = OneColors.WHITE,
    ) -> None:
        if not callable(get_current):
            raise ValueError("`get_current` must be a callable returning int")

        self._value_getters[name] = get_current

        def render():
            get_current_ = self._value_getters[name]
            current_value = get_current_()
            if current_value > total:
                raise ValueError(
                    f"Current value {current_value} is greater than total value {total}"
                )
            text = f"{label}: {current_value}/{total}"
            return HTML(
                f"<style fg='{fg}' bg='{bg}'>{text:^{self.space}}</style>"
            )

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
        if not callable(get_state):
            raise ValueError("`get_state` must be a callable returning bool")
        if not callable(toggle_state):
            raise ValueError("`toggle_state` must be a callable")
        key = key.upper()
        if key in self.toggle_keys:
            raise ValueError(f"Key {key} is already used as a toggle")
        if self.key_validator and not self.key_validator(key):
            raise ValueError(f"Key '{key}' conflicts with existing command, toggle, or reserved key.")
        self._value_getters[key] = get_state
        self.toggle_keys.append(key)

        def render():
            get_state_ = self._value_getters[key]
            color = bg_on if get_state_() else bg_off
            status = "ON" if get_state_() else "OFF"
            text = f"({key.upper()}) {label}: {status}"
            return HTML(
                f"<style bg='{color}' fg='{fg}'>{text:^{self.space}}</style>"
            )

        self._add_named(key, render)

        for k in (key.upper(), key.lower()):

            @self.key_bindings.add(k)
            def _(event):
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
        if name not in self._value_getters:
            raise ValueError(f"No value getter registered under name: '{name}'")
        return self._value_getters[name]()

    def _add_named(self, name: str, render_fn: Callable[[], HTML]) -> None:
        if name in self._named_items:
            raise ValueError(f"Bottom bar item '{name}' already exists")
        self._named_items[name] = render_fn
        self._items = list(self._named_items.values())

    def render(self):
        return merge_formatted_text([fn() for fn in self._items])
