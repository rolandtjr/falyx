# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""config.py
Configuration loader for Falyx CLI commands."""

import importlib
from pathlib import Path
from typing import Any

import toml
import yaml

from falyx.action import Action, BaseAction
from falyx.command import Command
from falyx.retry import RetryPolicy


def wrap_if_needed(obj: Any, name=None) -> BaseAction | Command:
    if isinstance(obj, (BaseAction, Command)):
        return obj
    elif callable(obj):
        return Action(name=name or getattr(obj, "__name__", "unnamed"), action=obj)
    else:
        raise TypeError(
            f"Cannot wrap object of type '{type(obj).__name__}' as a BaseAction or Command. "
            "It must be a callable or an instance of BaseAction."
        )


def import_action(dotted_path: str) -> Any:
    """Dynamically imports a callable from a dotted path like 'my.module.func'."""
    module_path, _, attr = dotted_path.rpartition(".")
    if not module_path:
        raise ValueError(f"Invalid action path: {dotted_path}")
    module = importlib.import_module(module_path)
    return getattr(module, attr)


def loader(file_path: str) -> list[dict[str, Any]]:
    """
    Load command definitions from a YAML or TOML file.

    Each command should be defined as a dictionary with at least:
    - key: a unique single-character key
    - description: short description
    - action: dotted import path to the action function/class

    Args:
        file_path (str): Path to the config file (YAML or TOML).

    Returns:
        list[dict[str, Any]]: A list of command configuration dictionaries.

    Raises:
        ValueError: If the file format is unsupported or file cannot be parsed.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"No such config file: {file_path}")

    suffix = path.suffix
    with path.open("r", encoding="UTF-8") as config_file:
        if suffix in (".yaml", ".yml"):
            raw_config = yaml.safe_load(config_file)
        elif suffix == ".toml":
            raw_config = toml.load(config_file)
        else:
            raise ValueError(f"Unsupported config format: {suffix}")

    if not isinstance(raw_config, list):
        raise ValueError("Configuration file must contain a list of command definitions.")

    required = ["key", "description", "action"]
    commands = []
    for entry in raw_config:
        for field in required:
            if field not in entry:
                raise ValueError(f"Missing '{field}' in command entry: {entry}")

        command_dict = {
            "key": entry["key"],
            "description": entry["description"],
            "action": wrap_if_needed(
                import_action(entry["action"]), name=entry["description"]
            ),
            "args": tuple(entry.get("args", ())),
            "kwargs": entry.get("kwargs", {}),
            "hidden": entry.get("hidden", False),
            "aliases": entry.get("aliases", []),
            "help_text": entry.get("help_text", ""),
            "color": entry.get("color", "white"),
            "confirm": entry.get("confirm", False),
            "confirm_message": entry.get("confirm_message", "Are you sure?"),
            "preview_before_confirm": entry.get("preview_before_confirm", True),
            "spinner": entry.get("spinner", False),
            "spinner_message": entry.get("spinner_message", "Processing..."),
            "spinner_type": entry.get("spinner_type", "dots"),
            "spinner_style": entry.get("spinner_style", "cyan"),
            "spinner_kwargs": entry.get("spinner_kwargs", {}),
            "before_hooks": entry.get("before_hooks", []),
            "success_hooks": entry.get("success_hooks", []),
            "error_hooks": entry.get("error_hooks", []),
            "after_hooks": entry.get("after_hooks", []),
            "teardown_hooks": entry.get("teardown_hooks", []),
            "retry": entry.get("retry", False),
            "retry_all": entry.get("retry_all", False),
            "retry_policy": RetryPolicy(**entry.get("retry_policy", {})),
            "tags": entry.get("tags", []),
            "logging_hooks": entry.get("logging_hooks", False),
            "requires_input": entry.get("requires_input", None),
        }
        commands.append(command_dict)

    return commands
