# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""protocols.py"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Protocol, runtime_checkable

from falyx.action.base_action import BaseAction


@runtime_checkable
class ActionFactoryProtocol(Protocol):
    async def __call__(
        self, *args: Any, **kwargs: Any
    ) -> Callable[..., Awaitable[BaseAction]]: ...


@runtime_checkable
class ArgParserProtocol(Protocol):
    def __call__(self, args: list[str]) -> tuple[tuple, dict]: ...
