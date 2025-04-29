"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""
import logging

from .action import Action, ActionGroup, ChainedAction, ProcessAction
from .command import Command
from .context import ExecutionContext, ResultsContext
from .execution_registry import ExecutionRegistry
from .falyx import Falyx

logger = logging.getLogger("falyx")

__version__ = "0.1.0"

__all__ = [
    "Action",
    "ChainedAction",
    "ActionGroup",
    "ProcessAction",
    "Falyx",
    "Command",
    "ExecutionContext",
    "ResultsContext",
    "ExecutionRegistry",
]
