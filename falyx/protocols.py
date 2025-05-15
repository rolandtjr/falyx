# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""protocols.py"""
from __future__ import annotations

from typing import Any, Awaitable, Protocol

from falyx.action.action import BaseAction


class ActionFactoryProtocol(Protocol):
    async def __call__(self, *args: Any, **kwargs: Any) -> Awaitable[BaseAction]: ...
