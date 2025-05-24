# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""http_action.py
Defines an Action subclass for making HTTP requests using aiohttp within Falyx workflows.

Features:
- Automatic reuse of aiohttp.ClientSession via SharedContext
- JSON, query param, header, and body support
- Retry integration and last_result injection
- Clean resource teardown using hooks
"""
from typing import Any

import aiohttp
from rich.tree import Tree

from falyx.action.action import Action
from falyx.context import ExecutionContext, SharedContext
from falyx.hook_manager import HookManager, HookType
from falyx.logger import logger
from falyx.themes import OneColors


async def close_shared_http_session(context: ExecutionContext) -> None:
    try:
        shared_context: SharedContext = context.get_shared_context()
        session = shared_context.get("http_session")
        should_close = shared_context.get("_session_should_close", False)
        if session and should_close:
            await session.close()
    except Exception as error:
        logger.warning("Error closing shared HTTP session: %s", error)


class HTTPAction(Action):
    """
    An Action for executing HTTP requests using aiohttp with shared session reuse.

    This action integrates seamlessly into Falyx pipelines, with automatic session
    management, result injection, and lifecycle hook support. It is ideal for CLI-driven
    API workflows where you need to call remote services and process their responses.

    Features:
    - Uses aiohttp for asynchronous HTTP requests
    - Reuses a shared session via SharedContext to reduce connection overhead
    - Automatically closes the session at the end of an ActionGroup (if applicable)
    - Supports GET, POST, PUT, DELETE, etc. with full header, query, body support
    - Retry and result injection compatible

    Args:
        name (str): Name of the action.
        method (str): HTTP method (e.g., 'GET', 'POST').
        url (str): The request URL.
        headers (dict[str, str], optional): Request headers.
        params (dict[str, Any], optional): URL query parameters.
        json (dict[str, Any], optional): JSON body to send.
        data (Any, optional): Raw data or form-encoded body.
        hooks (HookManager, optional): Hook manager for lifecycle events.
        inject_last_result (bool): Enable last_result injection.
        inject_into (str): Name of injected key.
        retry (bool): Enable retry logic.
        retry_policy (RetryPolicy): Retry settings.
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
        inject_into: str = "last_result",
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
            inject_into=inject_into,
            retry=retry,
            retry_policy=retry_policy,
        )

    async def _request(self, *_, **__) -> dict[str, Any]:
        if self.shared_context:
            context: SharedContext = self.shared_context
            session = context.get("http_session")
            if session is None:
                session = aiohttp.ClientSession()
                context.set("http_session", session)
                context.set("_session_should_close", True)
        else:
            session = aiohttp.ClientSession()

        try:
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
        finally:
            if not self.shared_context:
                await session.close()

    def register_teardown(self, hooks: HookManager):
        hooks.register(HookType.ON_TEARDOWN, close_shared_http_session)

    async def preview(self, parent: Tree | None = None):
        label = [
            f"[{OneColors.CYAN_b}]🌐 HTTPAction[/] '{self.name}'",
            f"\n[dim]Method:[/] {self.method}",
            f"\n[dim]URL:[/] {self.url}",
        ]
        if self.inject_last_result:
            label.append(f"\n[dim]Injects:[/] '{self.inject_into}'")
        if self.retry_policy and self.retry_policy.enabled:
            label.append(
                f"\n[dim]↻ Retries:[/] {self.retry_policy.max_retries}x, "
                f"delay {self.retry_policy.delay}s, backoff {self.retry_policy.backoff}x"
            )

        if parent:
            parent.add("".join(label))
        else:
            self.console.print(Tree("".join(label)))

    def __str__(self):
        return (
            f"HTTPAction(name={self.name!r}, method={self.method!r}, url={self.url!r}, "
            f"headers={self.headers!r}, params={self.params!r}, json={self.json!r}, "
            f"data={self.data!r}, retry={self.retry_policy.enabled}, "
            f"inject_last_result={self.inject_last_result})"
        )
