# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
import types
from datetime import datetime
from enum import EnumMeta
from typing import Any, Literal, Union, get_args, get_origin

from dateutil import parser as date_parser

from falyx.action.base_action import BaseAction
from falyx.logger import logger
from falyx.parser.signature import infer_args_from_func


def coerce_bool(value: str) -> bool:
    if isinstance(value, bool):
        return value
    value = value.strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    elif value in {"false", "0", "no", "off"}:
        return False
    return bool(value)


def coerce_enum(value: Any, enum_type: EnumMeta) -> Any:
    if isinstance(value, enum_type):
        return value

    if isinstance(value, str):
        try:
            return enum_type[value]
        except KeyError:
            pass

    base_type = type(next(iter(enum_type)).value)
    try:
        coerced_value = base_type(value)
        return enum_type(coerced_value)
    except (ValueError, TypeError):
        values = [str(enum.value) for enum in enum_type]
        raise ValueError(f"'{value}' should be one of {{{', '.join(values)}}}") from None


def coerce_value(value: str, target_type: type) -> Any:
    origin = get_origin(target_type)
    args = get_args(target_type)

    if origin is Literal:
        if value not in args:
            raise ValueError(
                f"Value '{value}' is not a valid literal for type {target_type}"
            )
        return value

    if isinstance(target_type, types.UnionType) or get_origin(target_type) is Union:
        for arg in args:
            try:
                return coerce_value(value, arg)
            except Exception:
                continue
        raise ValueError(f"Value '{value}' could not be coerced to any of {args}")

    if isinstance(target_type, EnumMeta):
        return coerce_enum(value, target_type)

    if target_type is bool:
        return coerce_bool(value)

    if target_type is datetime:
        try:
            return date_parser.parse(value)
        except ValueError as e:
            raise ValueError(f"Value '{value}' could not be parsed as a datetime") from e

    return target_type(value)


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
