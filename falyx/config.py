# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""config.py
Configuration loader for Falyx CLI commands."""

import importlib
import sys
from pathlib import Path
from typing import Any

import toml
import yaml
from rich.console import Console

from falyx.action import Action, BaseAction
from falyx.command import Command
from falyx.retry import RetryPolicy
from falyx.themes.colors import OneColors
from falyx.utils import logger

console = Console(color_system="auto")


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
        console.print(f"[{OneColors.DARK_RED}]❌ Invalid action path:[/] {dotted_path}")
        sys.exit(1)
    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as error:
        logger.error("Failed to import module '%s': %s", module_path, error)
        console.print(
            f"[{OneColors.DARK_RED}]❌ Could not import '{dotted_path}': {error}[/]\n"
            f"[{OneColors.COMMENT_GREY}]Ensure the module is installed and discoverable via PYTHONPATH."
        )
        sys.exit(1)
    try:
        action = getattr(module, attr)
    except AttributeError as error:
        logger.error(
            "Module '%s' does not have attribute '%s': %s", module_path, attr, error
        )
        console.print(
            f"[{OneColors.DARK_RED}]❌ Module '{module_path}' has no attribute '{attr}': {error}[/]"
        )
        sys.exit(1)
    return action


def loader(file_path: Path | str) -> list[dict[str, Any]]:
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
    if isinstance(file_path, str):
        path = Path(file_path)
    elif isinstance(file_path, Path):
        path = file_path
    else:
        raise TypeError("file_path must be a string or Path object.")

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
            "style": entry.get("style", "white"),
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
