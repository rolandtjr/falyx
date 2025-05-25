from typing import Any

from falyx.action.base import BaseAction
from falyx.logger import logger
from falyx.parsers.signature import infer_args_from_func


def same_argument_definitions(
    actions: list[Any],
    arg_metadata: dict[str, str | dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:

    arg_sets = []
    for action in actions:
        if isinstance(action, BaseAction):
            infer_target, _ = action.get_infer_target()
            arg_defs = infer_args_from_func(infer_target, arg_metadata)
        elif callable(action):
            arg_defs = infer_args_from_func(action, arg_metadata)
        else:
            logger.debug("Auto args unsupported for action: %s", action)
            return None
        arg_sets.append(arg_defs)

    first = arg_sets[0]
    if all(arg_set == first for arg_set in arg_sets[1:]):
        return first
    return None
