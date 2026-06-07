import pytest

from falyx import Falyx
from falyx.routing import RouteKind, RouteResult


@pytest.mark.asyncio
async def test_dispatch_seeds_namespace_defaults_into_default_namespace(
    monkeypatch,
):
    flx = Falyx(program="falyx")
    command = flx.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    route = RouteResult(
        kind=RouteKind.COMMAND,
        namespace=flx,
        context=flx.get_current_invocation_context(),
        command=command,
        namespace_defaults={"region": "us-east"},
        namespace_overrides={},
    )

    seen = {}

    async def fake_execute(*, command, args, kwargs, execution_args, **_):
        seen["region"] = flx.options_manager.get("region", None, "default")
        return "ok"

    monkeypatch.setattr(flx._executor, "execute", fake_execute)

    result = await flx._dispatch_route(
        route=route,
        args=(),
        kwargs={},
        execution_args={},
    )

    assert result == "ok"
    assert seen["region"] == "us-east"

    assert flx.options_manager.get("region", None, "default") == "us-east"


@pytest.mark.asyncio
async def test_dispatch_applies_namespace_overrides_temporarily_in_default_namespace(
    monkeypatch,
):
    flx = Falyx(program="falyx")
    command = flx.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    flx.options_manager.set("region", "us-east", "default")

    route = RouteResult(
        kind=RouteKind.COMMAND,
        namespace=flx,
        context=flx.get_current_invocation_context(),
        command=command,
        namespace_defaults={},
        namespace_overrides={"region": "us-west"},
    )

    seen = {}

    async def fake_execute(*, command, args, kwargs, execution_args, **_):
        seen["region"] = flx.options_manager.get("region", None, "default")
        return "ok"

    monkeypatch.setattr(flx._executor, "execute", fake_execute)

    result = await flx._dispatch_route(
        route=route,
        args=(),
        kwargs={},
        execution_args={},
        raise_on_error=False,
        wrap_errors=True,
    )

    assert result == "ok"
    assert seen["region"] == "us-west"

    assert flx.options_manager.get("region", None, "default") == "us-east"


@pytest.mark.asyncio
async def test_namespace_overrides_do_not_leak_after_command_execution(monkeypatch):
    flx = Falyx(program="falyx")
    command = flx.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    flx.options_manager.set("profile", "dev", "default")

    route = RouteResult(
        kind=RouteKind.COMMAND,
        namespace=flx,
        context=flx.get_current_invocation_context(),
        command=command,
        namespace_defaults={"region": "us-east"},
        namespace_overrides={"profile": "prod"},
    )

    async def fake_execute(*, command, args, kwargs, execution_args, **_):
        assert flx.options_manager.get("region", None, "default") == "us-east"
        assert flx.options_manager.get("profile", None, "default") == "prod"
        return "ok"

    monkeypatch.setattr(flx._executor, "execute", fake_execute)

    result = await flx._dispatch_route(
        route=route,
        args=(),
        kwargs={},
        execution_args={},
        raise_on_error=False,
        wrap_errors=True,
    )

    assert result == "ok"

    assert flx.options_manager.get("region", None, "default") == "us-east"
    assert flx.options_manager.get("profile", None, "default") == "dev"
