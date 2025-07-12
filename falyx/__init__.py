"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""

import logging

from .execution_registry import ExecutionRegistry
from .falyx import Falyx

logger = logging.getLogger("falyx")


__all__ = [
    "Falyx",
    "ExecutionRegistry",
]
