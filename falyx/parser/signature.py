# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
import inspect
from typing import Any, Callable

from falyx.logger import logger


def infer_args_from_func(
    func: Callable[[Any], Any] | None,
    arg_metadata: dict[str, str | dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Infer argument definitions from a callable's signature.
    Returns a list of kwargs suitable for CommandArgumentParser.add_argument.
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
            else:
                action = "store_false"

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
            }
        )

    return arg_defs
