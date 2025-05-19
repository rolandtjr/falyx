from typing import Any

from falyx import logger
from falyx.action.action import Action, ChainedAction, ProcessAction
from falyx.parsers.signature import infer_args_from_func


def same_argument_definitions(
    actions: list[Any],
    arg_metadata: dict[str, str | dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    arg_sets = []
    for action in actions:
        if isinstance(action, (Action, ProcessAction)):
            arg_defs = infer_args_from_func(action.action, arg_metadata)
        elif isinstance(action, ChainedAction):
            if action.actions:
                action = action.actions[0]
                if isinstance(action, Action):
                    arg_defs = infer_args_from_func(action.action, arg_metadata)
                elif callable(action):
                    arg_defs = infer_args_from_func(action, arg_metadata)
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
