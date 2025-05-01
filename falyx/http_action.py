from typing import Any

import aiohttp
from rich.tree import Tree

from falyx.action import Action
from falyx.context import ExecutionContext, SharedContext
from falyx.themes.colors import OneColors
from falyx.utils import logger


async def close_shared_http_session(context: ExecutionContext) -> None:
    try:
        shared_context: SharedContext = context.get_shared_context()
        session = shared_context.get("http_session")
        should_close = shared_context.get("_session_should_close", False)
        if session and should_close:
            await session.close()
    except Exception as error:
        logger.warning("⚠️ Error closing shared HTTP session: %s", error)


class HTTPAction(Action):
    """
    Specialized Action that performs an HTTP request using aiohttp and the shared context.

    Automatically reuses a shared aiohttp.ClientSession stored in SharedContext.
    Closes the session at the end of the ActionGroup (via an after-hook).
    """
    def __init__(
        self,
        name: str,
        method: str,
        url: str,
        *,
        args: tuple[Any, ...] = (),
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        data: Any = None,
        hooks=None,
        inject_last_result: bool = False,
        inject_last_result_as: str = "last_result",
        retry: bool = False,
        retry_policy=None,
    ):
        self.method = method.upper()
        self.url = url
        self.headers = headers
        self.params = params
        self.json = json
        self.data = data

        super().__init__(
            name=name,
            action=self._request,
            args=args,
            kwargs={},
            hooks=hooks,
            inject_last_result=inject_last_result,
            inject_last_result_as=inject_last_result_as,
            retry=retry,
            retry_policy=retry_policy,
        )

    async def _request(self, *args, **kwargs) -> dict[str, Any]:
        assert self.shared_context is not None, "SharedContext is not set"
        context: SharedContext = self.shared_context

        session = context.get("http_session")
        if session is None:
            session = aiohttp.ClientSession()
            context.set("http_session", session)
            context.set("_session_should_close", True)

        async with session.request(
            self.method,
            self.url,
            headers=self.headers,
            params=self.params,
            json=self.json,
            data=self.data,
        ) as response:
            body = await response.text()
            return {
                "status": response.status,
                "url": str(response.url),
                "headers": dict(response.headers),
                "body": body,
            }

    async def preview(self, parent: Tree | None = None):
        label = [
            f"[{OneColors.CYAN_b}]🌐 HTTPAction[/] '{self.name}'",
            f"\n[dim]Method:[/] {self.method}",
            f"\n[dim]URL:[/] {self.url}",
        ]
        if self.inject_last_result:
            label.append(f"\n[dim]Injects:[/] '{self.inject_last_result_as}'")
        if self.retry_policy and self.retry_policy.enabled:
            label.append(
                f"\n[dim]↻ Retries:[/] {self.retry_policy.max_retries}x, "
                f"delay {self.retry_policy.delay}s, backoff {self.retry_policy.backoff}x"
            )

        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))
