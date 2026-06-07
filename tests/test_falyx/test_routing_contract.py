import pytest

from falyx import Falyx
from falyx.routing import RouteKind


@pytest.mark.asyncio
async def test_resolve_route_carries_root_options_through_nested_namespace():
    child = Falyx(program="child")
    child.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    root = Falyx(program="root")
    root.add_submenu(
        key="C",
        description="Child Menu",
        submenu=child,
    )

    route = await root.resolve_route(
        ["--verbose", "C", "D"],
        invocation_context=root.get_current_invocation_context(),
    )

    assert route.context.typed_path[-2:] == ["C", "D"]

    assert route.kind is RouteKind.COMMAND
    assert route.namespace is child
    assert route.command is child.commands["D"]
    assert route.leaf_argv == []

    assert route.root_overrides == {"verbose": True}
    assert route.root_defaults["verbose"] is False
    assert route.root_defaults["debug_hooks"] is False
    assert route.root_defaults["never_prompt"] is False

    assert route.namespace_overrides == {}


@pytest.mark.asyncio
async def test_resolve_route_returns_unknown_when_only_namespace_options_are_provided():
    flx = Falyx(program="falyx")
    flx.add_option("--profile", default="dev")

    route = await flx.resolve_route(
        ["--profile", "prod"],
        invocation_context=flx.get_current_invocation_context(),
    )

    assert route.kind is RouteKind.UNKNOWN
    assert route.namespace is flx
    assert route.command is None
    assert route.current_head == ""
    assert route.is_preview is False
    assert route.root_defaults == {}
    assert route.root_overrides == {}
    assert route.namespace_defaults == {}
    assert route.namespace_overrides == {}


@pytest.mark.asyncio
async def test_resolve_route_returns_unknown_when_only_root_options_are_provided():
    flx = Falyx(program="falyx")

    route = await flx.resolve_route(
        ["--verbose"],
        invocation_context=flx.get_current_invocation_context(),
    )

    assert route.kind is RouteKind.UNKNOWN
    assert route.namespace is flx
    assert route.command is None
    assert route.current_head == ""
    assert route.is_preview is False


@pytest.mark.asyncio
async def test_resolve_route_returns_unknown_when_nested_namespace_consumes_only_options():
    child = Falyx(program="child")
    child.add_option("--region", default="us-east")

    root = Falyx(program="root")
    root.add_submenu(key="C", description="Child", submenu=child)

    route = await root.resolve_route(
        ["C", "--region", "us-west"],
        invocation_context=root.get_current_invocation_context(),
    )

    assert route.kind is RouteKind.UNKNOWN
    assert route.namespace is child
    assert route.command is None
    assert route.context.typed_path[-1] == "C"
