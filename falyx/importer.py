"""importer.py"""

import importlib
from types import ModuleType
from typing import Any, Callable


def resolve_action(path: str) -> Callable[..., Any]:
    """
    Resolve a dotted path to a Python callable.
    Example: 'mypackage.mymodule.myfunction'

    Raises:
        ImportError if the module or function does not exist.
        ValueError if the resolved attribute is not callable.
    """
    if ":" in path:
        module_path, function_name = path.split(":")
    else:
        *module_parts, function_name = path.split(".")
        module_path = ".".join(module_parts)

    module: ModuleType = importlib.import_module(module_path)
    function: Any = getattr(module, function_name)

    if not callable(function):
        raise ValueError(f"Resolved attribute '{function_name}' is not callable.")

    return function
