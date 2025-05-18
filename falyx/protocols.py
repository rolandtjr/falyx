# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""protocols.py"""
from __future__ import annotations

from typing import Any, Awaitable, Protocol, runtime_checkable

from falyx.action.action import BaseAction


@runtime_checkable
class ActionFactoryProtocol(Protocol):
    async def __call__(self, *args: Any, **kwargs: Any) -> Awaitable[BaseAction]: ...


@runtime_checkable
class ArgParserProtocol(Protocol):
    def __call__(self, args: list[str]) -> tuple[tuple, dict]: ...
