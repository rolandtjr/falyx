# Falyx CLI Framework — (c) 2026 rtj.dev LLC — MIT Licensed
"""Option state management for Falyx CLI runtimes.

This module defines `OptionsManager`, a small utility responsible for
storing, retrieving, and temporarily overriding runtime option values across
named namespaces.

Falyx uses this manager to hold global session- and execution-scoped flags such
as verbosity, prompt suppression, confirmation behavior, and other mutable
runtime settings. Options are stored in isolated namespace dictionaries so
different layers of the runtime can share one manager without clobbering each
other's state.

In addition to basic get/set operations, the manager provides helpers for:

- toggling boolean flags
- exposing option access as zero-argument callables for UI bindings
- temporarily overriding a namespace within a context manager
- holding a shared `SpinnerManager` for spinner lifecycle integration

Typical usage:
    ```
    options = OptionsManager()
    options.from_mapping({"verbose": True})
    if options.get("verbose"):
        ...

    with options.override_namespace({"skip_confirm": True}, "execution"):
        ...
    ```

Attributes:
    options (defaultdict[str, dict[str, Any]]): Mapping of namespace names to
        option dictionaries.
    spinners (SpinnerManager): Shared spinner manager available to runtime
        components that need coordinated spinner rendering.
"""
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Mapping

from falyx.logger import logger
from falyx.spinner_manager import SpinnerManager


class OptionsManager:
    """Manage mutable option values across named runtime namespaces.

    `OptionsManager` is the central store for Falyx runtime flags. Each option
    is stored under a namespace name such as `"default"` or `"execution"`,
    allowing global settings and temporary execution-scoped overrides to
    coexist in one shared object.

    The manager supports direct reads and writes, boolean toggling, namespace
    snapshots, and temporary override contexts. It also exposes small callable
    wrappers that are useful when integrating option reads or toggles into UI
    components such as bottom-bar controls or key bindings.

    Args:
        namespaces (list[tuple[str, dict[str, Any]]] | None): Optional initial
            namespace/value pairs to preload into the manager.

    Attributes:
        options (defaultdict[str, dict[str, Any]]): Internal namespace-to-option
            mapping.
        spinners (SpinnerManager): Shared spinner manager used by other Falyx
            runtime components.
    """

    def __init__(
        self,
        namespaces: list[tuple[str, dict[str, Any]]] | None = None,
    ) -> None:
        """Initialize the option manager.

        Args:
            namespaces (list[tuple[str, dict[str, Any]]] | None): Optional list
                of `(namespace_name, values)` pairs to load during
                initialization.
        """
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
        """Merge option values into a namespace.

        Existing keys in the target namespace are updated in place. Missing
        namespaces are created automatically.

        Args:
            values (Mapping[str, Any]): Mapping of option names to values.
            namespace_name (str): Target namespace to update. Defaults to
                `"default"`.
        """
        self.options[namespace_name].update(dict(values))

    def get(
        self,
        option_name: str,
        default: Any = None,
        namespace_name: str = "default",
    ) -> Any:
        """Return an option value from a namespace.

        Args:
            option_name (str): Name of the option to retrieve.
            default (Any): Value to return when the option is not present.
                Defaults to `None`.
            namespace_name (str): Namespace to read from. Defaults to
                `"default"`.

        Returns:
            Any: The stored option value if present, otherwise `default`.
        """
        return self.options[namespace_name].get(option_name, default)

    def set(
        self,
        option_name: str,
        value: Any,
        namespace_name: str = "default",
    ) -> None:
        """Store an option value in a namespace.

        Args:
            option_name (str): Name of the option to set.
            value (Any): Value to store.
            namespace_name (str): Namespace to update. Defaults to `"default"`.
        """
        self.options[namespace_name][option_name] = value

    def has_option(
        self,
        option_name: str,
        namespace_name: str = "default",
    ) -> bool:
        """Return whether an option exists in a namespace.

        Args:
            option_name (str): Name of the option to check.
            namespace_name (str): Namespace to inspect. Defaults to `"default"`.

        Returns:
            bool: `True` if the option exists in the namespace, otherwise
            `False`.
        """
        return option_name in self.options[namespace_name]

    def toggle(
        self,
        option_name: str,
        namespace_name: str = "default",
    ) -> None:
        """Invert a boolean option in place.

        Args:
            option_name (str): Name of the option to toggle.
            namespace_name (str): Namespace containing the option. Defaults to
                `"default"`.

        Raises:
            TypeError: If the target option is missing or is not a boolean.
        """
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
        """Return a zero-argument callable that reads an option value.

        This is useful for UI integrations that expect a callback instead of an
        eagerly evaluated value.

        Args:
            option_name (str): Name of the option to read.
            namespace_name (str): Namespace to read from. Defaults to
                `"default"`.

        Returns:
            Callable[[], Any]: Function that returns the current option value
            when called.
        """

        def _getter() -> Any:
            return self.get(option_name, namespace_name=namespace_name)

        return _getter

    def get_toggle_function(
        self,
        option_name: str,
        namespace_name: str = "default",
    ) -> Callable[[], None]:
        """Return a zero-argument callable that toggles a boolean option.

        This is useful for key bindings, bottom-bar toggles, or other UI hooks
        that need a callable action.

        Args:
            option_name (str): Name of the boolean option to toggle.
            namespace_name (str): Namespace containing the option. Defaults to
                `"default"`.

        Returns:
            Callable[[], None]: Function that toggles the option when called.
        """

        def _toggle() -> None:
            self.toggle(option_name, namespace_name=namespace_name)

        return _toggle

    def get_namespace_dict(self, namespace_name: str) -> dict[str, Any]:
        """Return a shallow copy of one namespace's option dictionary.

        Args:
            namespace_name (str): Namespace to snapshot.

        Returns:
            dict[str, Any]: Copy of the namespace's stored options.

        Raises:
            ValueError: If the requested namespace does not exist.
        """
        if namespace_name not in self.options:
            raise ValueError(f"Namespace '{namespace_name}' not found.")
        return dict(self.options[namespace_name])

    @contextmanager
    def override_namespace(
        self,
        overrides: Mapping[str, Any],
        namespace_name: str = "execution",
    ) -> Iterator[None]:
        """Temporarily apply option overrides within a namespace.

        The current namespace contents are copied before the overrides are
        applied. When the context exits, the original namespace state is
        restored, even if an exception is raised inside the context block.

        Args:
            overrides (Mapping[str, Any]): Temporary option values to merge into
                the namespace.
            namespace_name (str): Namespace to override. Defaults to
                `"execution"`.

        Yields:
            None: Control is yielded to the wrapped context block.

        Raises:
            ValueError: If the namespace does not already exist.
        """
        original = self.get_namespace_dict(namespace_name)
        try:
            self.from_mapping(values=overrides, namespace_name=namespace_name)
            yield
        finally:
            self.options[namespace_name] = original
