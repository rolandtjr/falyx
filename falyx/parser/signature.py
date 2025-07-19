# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Provides utilities for introspecting Python callables and extracting argument
metadata compatible with Falyx's `CommandArgumentParser`.

This module is primarily used to auto-generate command argument definitions from
function signatures, enabling seamless integration of plain functions into the
Falyx CLI with minimal boilerplate.

Functions:
- infer_args_from_func: Generate a list of argument definitions based on a function's signature.
"""
import inspect
from typing import Any, Callable

from falyx.logger import logger


def infer_args_from_func(
    func: Callable[[Any], Any] | None,
    arg_metadata: dict[str, str | dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Infer CLI-style argument definitions from a function signature.

    This utility inspects the parameters of a function and returns a list of dictionaries,
    each of which can be passed to `CommandArgumentParser.add_argument()`.

    Args:
        func (Callable | None): The function to inspect.
        arg_metadata (dict | None): Optional metadata overrides for help text, type hints,
                                    choices, and suggestions for each parameter.

    Returns:
        list[dict[str, Any]]: A list of argument definitions inferred from the function.
    """
    if not callable(func):
        logger.debug("Provided argument is not callable: %s", func)
        return []
    arg_metadata = arg_metadata or {}
    signature = inspect.signature(func)
    arg_defs = []

    for name, param in signature.parameters.items():
        raw_metadata = arg_metadata.get(name, {})
        metadata = (
            {"help": raw_metadata} if isinstance(raw_metadata, str) else raw_metadata
        )
        if param.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            continue

        if metadata.get("type"):
            arg_type = metadata["type"]
        else:
            arg_type = (
                param.annotation
                if param.annotation is not inspect.Parameter.empty
                else str
            )
            if isinstance(arg_type, str):
                arg_type = str
        default = param.default if param.default is not inspect.Parameter.empty else None
        is_required = param.default is inspect.Parameter.empty
        if is_required:
            flags = [f"{name.replace('_', '-')}"]
        else:
            flags = [f"--{name.replace('_', '-')}"]
        action = "store"
        nargs: int | str | None = None

        if arg_type is bool:
            if param.default is False:
                action = "store_true"
                default = None
            elif param.default is True:
                action = "store_false"
                default = None

        if arg_type is list:
            action = "append"
            if is_required:
                nargs = "+"
            else:
                nargs = "*"

        arg_defs.append(
            {
                "flags": flags,
                "dest": name,
                "type": arg_type,
                "default": default,
                "required": is_required,
                "nargs": nargs,
                "action": action,
                "help": metadata.get("help", ""),
                "choices": metadata.get("choices"),
                "suggestions": metadata.get("suggestions"),
            }
        )

    return arg_defs
