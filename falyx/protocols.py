# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines structural protocols for advanced Falyx features.

These runtime-checkable `Protocol` classes specify the expected interfaces for:
- Factories that asynchronously return actions
- Argument parsers used in dynamic command execution

Used to support type-safe extensibility and plugin-like behavior without requiring
explicit base classes.

Protocols:
- ActionFactoryProtocol: Async callable that returns a coroutine yielding a BaseAction.
- ArgParserProtocol: Callable that accepts CLI-style args and returns (args, kwargs) tuple.
"""
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
