# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""utils.py"""
import functools
import inspect
import logging
import os
import shutil
import sys
from itertools import islice
from typing import Any, Awaitable, Callable, TypeVar

import pythonjsonlogger.json
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import (
    AnyFormattedText,
    FormattedText,
    merge_formatted_text,
)
from rich.logging import RichHandler

from falyx.themes.colors import OneColors
from falyx.validators import yes_no_validator

logger = logging.getLogger("falyx")

T = TypeVar("T")


async def _noop(*args, **kwargs):
    pass


def get_program_invocation() -> str:
    """Returns the recommended program invocation prefix."""
    script = sys.argv[0]
    program = shutil.which(script)
    if program:
        return os.path.basename(program)

    executable = sys.executable
    if "python" in executable:
        return f"python {script}"
    return script


def is_coroutine(function: Callable[..., Any]) -> bool:
    return inspect.iscoroutinefunction(function)


def ensure_async(function: Callable[..., T]) -> Callable[..., Awaitable[T]]:
    if is_coroutine(function):
        return function  # type: ignore

    @functools.wraps(function)
    async def async_wrapper(*args, **kwargs) -> T:
        return function(*args, **kwargs)

    if not callable(function):
        raise TypeError(f"{function} is not callable")
    return async_wrapper


def chunks(iterator, size):
    """Yield successive n-sized chunks from an iterator."""
    iterator = iter(iterator)
    while True:
        chunk = list(islice(iterator, size))
        if not chunk:
            break
        yield chunk


async def confirm_async(
    message: AnyFormattedText = "Are you sure?",
    prefix: AnyFormattedText = FormattedText([(OneColors.CYAN, "❓ ")]),
    suffix: AnyFormattedText = FormattedText([(OneColors.LIGHT_YELLOW_b, " [Y/n] > ")]),
    session: PromptSession | None = None,
) -> bool:
    """Prompt the user with a yes/no async confirmation and return True for 'Y'."""
    session = session or PromptSession()
    merged_message: AnyFormattedText = merge_formatted_text([prefix, message, suffix])
    answer = await session.prompt_async(
        merged_message,
        validator=yes_no_validator(),
    )
    return True if answer.upper() == "Y" else False


class CaseInsensitiveDict(dict):
    """A case-insensitive dictionary that treats all keys as uppercase."""

    def _normalize_key(self, key):
        return key.upper() if isinstance(key, str) else key

    def __setitem__(self, key, value):
        super().__setitem__(self._normalize_key(key), value)

    def __getitem__(self, key):
        return super().__getitem__(self._normalize_key(key))

    def __contains__(self, key):
        return super().__contains__(self._normalize_key(key))

    def get(self, key, default=None):
        return super().get(self._normalize_key(key), default)

    def pop(self, key, default=None):
        return super().pop(self._normalize_key(key), default)

    def update(self, other=None, **kwargs):
        items = {}
        if other:
            items.update({self._normalize_key(k): v for k, v in other.items()})
        items.update({self._normalize_key(k): v for k, v in kwargs.items()})
        super().update(items)

    def __iter__(self):
        return super().__iter__()

    def keys(self):
        return super().keys()


def running_in_container() -> bool:
    try:
        with open("/proc/1/cgroup", "r", encoding="UTF-8") as f:
            content = f.read()
            return (
                "docker" in content
                or "kubepods" in content
                or "containerd" in content
                or "podman" in content
            )
    except Exception:
        return False


def setup_logging(
    mode: str | None = None,
    log_filename: str = "falyx.log",
    json_log_to_file: bool = False,
    file_log_level: int = logging.DEBUG,
    console_log_level: int = logging.WARNING,
):
    """
    Configure logging for Falyx with support for both CLI-friendly and structured JSON output.

    This function sets up separate logging handlers for console and file output, with optional
    support for JSON formatting. It also auto-detects whether the application is running inside
    a container to default to machine-readable logs when appropriate.

    Args:
        mode (str | None):
            Logging output mode. Can be:
                - "cli": human-readable Rich console logs (default outside containers)
                - "json": machine-readable JSON logs (default inside containers)
            If not provided, it will use the `FALYX_LOG_MODE` environment variable
            or fallback based on container detection.
        log_filename (str):
            Path to the log file for file-based logging output. Defaults to "falyx.log".
        json_log_to_file (bool):
            Whether to format file logs as JSON (structured) instead of plain text.
            Defaults to False.
        file_log_level (int):
            Logging level for file output. Defaults to `logging.DEBUG`.
        console_log_level (int):
            Logging level for console output. Defaults to `logging.WARNING`.

    Behavior:
        - Clears existing root handlers before setup.
        - Configures console logging using either Rich (for CLI) or JSON formatting.
        - Configures file logging in plain text or JSON based on `json_log_to_file`.
        - Automatically sets logging levels for noisy third-party modules (`urllib3`, `asyncio`).
        - Propagates logs from the "falyx" logger to ensure centralized output.

    Raises:
        ValueError: If an invalid logging `mode` is passed.

    Environment Variables:
        FALYX_LOG_MODE: Can override `mode` to enforce "cli" or "json" logging behavior.
    """
    if not mode:
        mode = os.getenv("FALYX_LOG_MODE") or (
            "json" if running_in_container() else "cli"
        )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    if root.hasHandlers():
        root.handlers.clear()

    if mode == "cli":
        console_handler: RichHandler | logging.StreamHandler = RichHandler(
            rich_tracebacks=True,
            show_time=True,
            show_level=True,
            show_path=False,
            markup=True,
            log_time_format="[%Y-%m-%d %H:%M:%S]",
        )
    elif mode == "json":
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(
            pythonjsonlogger.json.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s"
            )
        )
    else:
        raise ValueError(f"Invalid log mode: {mode}")

    console_handler.setLevel(console_log_level)
    root.addHandler(console_handler)

    file_handler = logging.FileHandler(log_filename)
    file_handler.setLevel(file_log_level)
    if json_log_to_file:
        file_handler.setFormatter(
            pythonjsonlogger.json.JsonFormatter(
                "%(asctime)s %(name)s %(levelname)s %(message)s"
            )
        )
    else:
        file_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(file_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("markdown_it").setLevel(logging.WARNING)

    logger = logging.getLogger("falyx")
    logger.propagate = True
    logger.debug("Logging initialized in '%s' mode.", mode)
