# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""config.py
Configuration loader for Falyx CLI commands."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

import toml
import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from falyx.action.action import Action
from falyx.action.base_action import BaseAction
from falyx.command import Command
from falyx.console import console
from falyx.falyx import Falyx
from falyx.logger import logger
from falyx.retry import RetryPolicy
from falyx.themes import OneColors


def wrap_if_needed(obj: Any, name=None) -> BaseAction | Command:
    if isinstance(obj, (BaseAction, Command)):
        return obj
    elif callable(obj):
        return Action(name=name or getattr(obj, "__name__", "unnamed"), action=obj)
    else:
        raise TypeError(
            f"Cannot wrap object of type '{type(obj).__name__}'. "
            "Expected a function or BaseAction."
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
            f"[{OneColors.COMMENT_GREY}]Ensure the module is installed and discoverable "
            "via PYTHONPATH."
        )
        sys.exit(1)
    try:
        action = getattr(module, attr)
    except AttributeError as error:
        logger.error(
            "Module '%s' does not have attribute '%s': %s", module_path, attr, error
        )
        console.print(
            f"[{OneColors.DARK_RED}]❌ Module '{module_path}' has no attribute "
            f"'{attr}': {error}[/]"
        )
        sys.exit(1)
    return action


class RawCommand(BaseModel):
    """Raw command model for Falyx CLI configuration."""

    key: str
    description: str
    action: str

    args: tuple[Any, ...] = Field(default_factory=tuple)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    aliases: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    style: str = OneColors.WHITE

    confirm: bool = False
    confirm_message: str = "Are you sure?"
    preview_before_confirm: bool = True

    spinner: bool = False
    spinner_message: str = "Processing..."
    spinner_type: str = "dots"
    spinner_style: str = OneColors.CYAN
    spinner_kwargs: dict[str, Any] = Field(default_factory=dict)

    before_hooks: list[Callable] = Field(default_factory=list)
    success_hooks: list[Callable] = Field(default_factory=list)
    error_hooks: list[Callable] = Field(default_factory=list)
    after_hooks: list[Callable] = Field(default_factory=list)
    teardown_hooks: list[Callable] = Field(default_factory=list)

    logging_hooks: bool = False
    retry: bool = False
    retry_all: bool = False
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    hidden: bool = False
    help_text: str = ""
    help_epilog: str = ""

    @field_validator("retry_policy")
    @classmethod
    def validate_retry_policy(cls, value: dict | RetryPolicy) -> RetryPolicy:
        if isinstance(value, RetryPolicy):
            return value
        if not isinstance(value, dict):
            raise ValueError("retry_policy must be a dictionary.")
        return RetryPolicy(**value)


def convert_commands(raw_commands: list[dict[str, Any]]) -> list[Command]:
    commands = []
    for entry in raw_commands:
        raw_command = RawCommand(**entry)
        commands.append(
            Command.model_validate(
                {
                    **raw_command.model_dump(exclude={"action"}),
                    "action": wrap_if_needed(
                        import_action(raw_command.action), name=raw_command.description
                    ),
                }
            )
        )

    return commands


def convert_submenus(
    raw_submenus: list[dict[str, Any]], *, parent_path: Path | None = None, depth: int = 0
) -> list[dict[str, Any]]:
    submenus: list[dict[str, Any]] = []
    for raw_submenu in raw_submenus:
        if raw_submenu.get("config"):
            config_path = Path(raw_submenu["config"])
            if parent_path:
                config_path = (parent_path.parent / config_path).resolve()
            submenu = loader(config_path, _depth=depth + 1)
        else:
            submenu_module_path = raw_submenu.get("submenu")
            if not isinstance(submenu_module_path, str):
                console.print(
                    f"[{OneColors.DARK_RED}]❌ Invalid submenu path:[/] {submenu_module_path}"
                )
                sys.exit(1)
            submenu = import_action(submenu_module_path)
        if not isinstance(submenu, Falyx):
            console.print(f"[{OneColors.DARK_RED}]❌ Invalid submenu:[/] {submenu}")
            sys.exit(1)

        key = raw_submenu.get("key")
        if not isinstance(key, str):
            console.print(f"[{OneColors.DARK_RED}]❌ Invalid submenu key:[/] {key}")
            sys.exit(1)

        description = raw_submenu.get("description")
        if not isinstance(description, str):
            console.print(
                f"[{OneColors.DARK_RED}]❌ Invalid submenu description:[/] {description}"
            )
            sys.exit(1)

        submenus.append(
            Submenu(
                key=key,
                description=description,
                submenu=submenu,
                style=raw_submenu.get("style", OneColors.CYAN),
            ).model_dump()
        )
    return submenus


class Submenu(BaseModel):
    """Submenu model for Falyx CLI configuration."""

    key: str
    description: str
    submenu: Any
    style: str = OneColors.CYAN


class FalyxConfig(BaseModel):
    """Falyx CLI configuration model."""

    title: str = "Falyx CLI"
    prompt: str | list[tuple[str, str]] | list[list[str]] = [
        (OneColors.BLUE_b, "FALYX > ")
    ]
    columns: int = 4
    welcome_message: str = ""
    exit_message: str = ""
    commands: list[Command] | list[dict] = []
    submenus: list[dict[str, Any]] = []

    @model_validator(mode="after")
    def validate_prompt_format(self) -> FalyxConfig:
        if isinstance(self.prompt, list):
            for pair in self.prompt:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    raise ValueError(
                        "Prompt list must contain 2-element (style, text) pairs"
                    )
        return self

    def to_falyx(self) -> Falyx:
        flx = Falyx(
            title=self.title,
            prompt=self.prompt,  # type: ignore[arg-type]
            columns=self.columns,
            welcome_message=self.welcome_message,
            exit_message=self.exit_message,
        )
        flx.add_commands(self.commands)
        for submenu in self.submenus:
            flx.add_submenu(**submenu)
        return flx


def loader(file_path: Path | str, _depth: int = 0) -> Falyx:
    """
    Load Falyx CLI configuration from a YAML or TOML file.

    The file should contain a dictionary with a list of commands.

    Each command should be defined as a dictionary with at least:
    - key: a unique single-character key
    - description: short description
    - action: dotted import path to the action function/class

    Args:
        file_path (str): Path to the config file (YAML or TOML).

    Returns:
        Falyx: An instance of the Falyx CLI with loaded commands.

    Raises:
        ValueError: If the file format is unsupported or file cannot be parsed.
    """
    if _depth > 5:
        raise ValueError("Maximum submenu depth exceeded (5 levels deep)")

    if isinstance(file_path, (str, Path)):
        path = Path(file_path)
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

    if not isinstance(raw_config, dict):
        raise ValueError(
            "Configuration file must contain a dictionary with a list of commands.\n"
            "Example:\n"
            "title: 'My CLI'\n"
            "commands:\n"
            "  - key: 'a'\n"
            "    description: 'Example command'\n"
            "    action: 'my_module.my_function'"
        )

    commands = convert_commands(raw_config["commands"])
    submenus = convert_submenus(raw_config.get("submenus", []))
    return FalyxConfig(
        title=raw_config.get("title", f"[{OneColors.BLUE_b}]Falyx CLI"),
        prompt=raw_config.get("prompt", [(OneColors.BLUE_b, "FALYX > ")]),
        columns=raw_config.get("columns", 4),
        welcome_message=raw_config.get("welcome_message", ""),
        exit_message=raw_config.get("exit_message", ""),
        commands=commands,
        submenus=submenus,
    ).to_falyx()
