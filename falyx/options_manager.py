# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Manages global or scoped CLI options across namespaces for Falyx commands.

The `OptionsManager` provides a centralized interface for retrieving, setting, toggling,
and introspecting options defined in `argparse.Namespace` objects. It is used internally
by Falyx to pass and resolve runtime flags like `--verbose`, `--force-confirm`, etc.

Each option is stored under a namespace key (e.g., "default", "user_config") to
support multiple sources of configuration.

Key Features:
- Safe getter/setter for typed option resolution
- Toggle support for boolean options (used by bottom bar toggles, etc.)
- Callable getter/toggler wrappers for dynamic UI bindings
- Namespace merging via `from_namespace`

Typical Usage:
    options = OptionsManager()
    options.from_namespace(args, namespace_name="default")
    if options.get("verbose"):
        ...
    options.toggle("force_confirm")
    value_fn = options.get_value_getter("dry_run")
    toggle_fn = options.get_toggle_function("debug")

Used by:
- Falyx CLI runtime configuration
- Bottom bar toggles
- Dynamic flag injection into commands and actions
"""
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping

from falyx.logger import logger
from falyx.spinner_manager import SpinnerManager


class OptionsManager:
    """Manages CLI option state across multiple argparse namespaces.

    Allows dynamic retrieval, setting, toggling, and introspection of command-line
    options. Supports named namespaces (e.g., "default") and is used throughout
    Falyx for runtime configuration and bottom bar toggle integration.
    """

    def __init__(
        self,
        namespaces: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        self.options: defaultdict = defaultdict(dict)
        self.spinners = SpinnerManager()
        if namespaces:
            for namespace_name, namespace in namespaces:
                self.from_mapping(namespace, namespace_name)

    def from_mapping(
        self,
        values: Mapping[str, Any],
        namespace_name: str = "default",
    ) -> None:
        """Load options from a mapping, optionally with a prefix for namespacing."""
        self.options[namespace_name].update(dict(values))

    def get(
        self,
        option_name: str,
        default: Any = None,
        namespace_name: str = "default",
    ) -> Any:
        """Get the value of an option."""
        return self.options[namespace_name].get(option_name, default)

    def set(
        self,
        option_name: str,
        value: Any,
        namespace_name: str = "default",
    ) -> None:
        """Set the value of an option."""
        self.options[namespace_name][option_name] = value

    def has_option(
        self,
        option_name: str,
        namespace_name: str = "default",
    ) -> bool:
        """Check if an option exists in the namespace."""
        return option_name in self.options[namespace_name]

    def toggle(
        self,
        option_name: str,
        namespace_name: str = "default",
    ) -> None:
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
        self,
        option_name: str,
        namespace_name: str = "default",
    ) -> Callable[[], Any]:
        """Get the value of an option as a getter function."""

        def _getter() -> Any:
            return self.get(option_name, namespace_name=namespace_name)

        return _getter

    def get_toggle_function(
        self,
        option_name: str,
        namespace_name: str = "default",
    ) -> Callable[[], None]:
        """Get the toggle function for a boolean option."""

        def _toggle() -> None:
            self.toggle(option_name, namespace_name=namespace_name)

        return _toggle

    def get_namespace_dict(self, namespace_name: str) -> dict[str, Any]:
        """Return all options in a namespace as a dictionary."""
        if namespace_name not in self.options:
            raise ValueError(f"Namespace '{namespace_name}' not found.")
        return dict(self.options[namespace_name])

    @contextmanager
    def override_namespace(
        self,
        overrides: Mapping[str, Any],
        namespace_name: str = "execution",
    ) -> Iterator[None]:
        """Temporarily override options in a namespace within a context."""
        original = self.get_namespace_dict(namespace_name)
        try:
            self.from_mapping(values=overrides, namespace_name=namespace_name)
            yield
        finally:
            self.options[namespace_name] = original
