# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""options_manager.py"""

from argparse import Namespace
from collections import defaultdict
from typing import Any, Callable

from falyx.logger import logger


class OptionsManager:
    """OptionsManager"""

    def __init__(self, namespaces: list[tuple[str, Namespace]] | None = None) -> None:
        self.options: defaultdict = defaultdict(Namespace)
        if namespaces:
            for namespace_name, namespace in namespaces:
                self.from_namespace(namespace, namespace_name)

    def from_namespace(
        self, namespace: Namespace, namespace_name: str = "cli_args"
    ) -> None:
        self.options[namespace_name] = namespace

    def get(
        self, option_name: str, default: Any = None, namespace_name: str = "cli_args"
    ) -> Any:
        """Get the value of an option."""
        return getattr(self.options[namespace_name], option_name, default)

    def set(self, option_name: str, value: Any, namespace_name: str = "cli_args") -> None:
        """Set the value of an option."""
        setattr(self.options[namespace_name], option_name, value)

    def has_option(self, option_name: str, namespace_name: str = "cli_args") -> bool:
        """Check if an option exists in the namespace."""
        return hasattr(self.options[namespace_name], option_name)

    def toggle(self, option_name: str, namespace_name: str = "cli_args") -> None:
        """Toggle a boolean option."""
        current = self.get(option_name, namespace_name=namespace_name)
        if not isinstance(current, bool):
            raise TypeError(
                f"Cannot toggle non-boolean option: '{option_name}' in '{namespace_name}'"
            )
        self.set(option_name, not current, namespace_name=namespace_name)
        logger.debug(
            "Toggled '%s' in '%s' to %s", option_name, namespace_name, not current
        )

    def get_value_getter(
        self, option_name: str, namespace_name: str = "cli_args"
    ) -> Callable[[], Any]:
        """Get the value of an option as a getter function."""

        def _getter() -> Any:
            return self.get(option_name, namespace_name=namespace_name)

        return _getter

    def get_toggle_function(
        self, option_name: str, namespace_name: str = "cli_args"
    ) -> Callable[[], None]:
        """Get the toggle function for a boolean option."""

        def _toggle() -> None:
            self.toggle(option_name, namespace_name=namespace_name)

        return _toggle

    def get_namespace_dict(self, namespace_name: str) -> Namespace:
        """Return all options in a namespace as a dictionary."""
        if namespace_name not in self.options:
            raise ValueError(f"Namespace '{namespace_name}' not found.")
        return vars(self.options[namespace_name])
