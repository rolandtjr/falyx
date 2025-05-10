from __future__ import annotations

from typing import Any, Protocol

from falyx.action import BaseAction


class ActionFactoryProtocol(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> BaseAction: ...
