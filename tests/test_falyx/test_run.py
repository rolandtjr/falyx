import asyncio
import sys

import pytest
from rich.text import Text

from falyx import Falyx
from falyx.console import console as falyx_console
from falyx.exceptions import FalyxError
from falyx.signals import BackSignal, CancelSignal, FlowSignal, HelpSignal, QuitSignal


async def throw_error_action(error: str):
    if error == "QuitSignal":
        raise QuitSignal("Quit signal triggered.")
    elif error == "BackSignal":
        raise BackSignal("Back signal triggered.")
    elif error == "CancelSignal":
        raise CancelSignal("Cancel signal triggered.")
    elif error == "ValueError":
        raise ValueError("This is a ValueError.")
    elif error == "HelpSignal":
        raise HelpSignal("Help signal triggered.")
    elif error == "FalyxError":
        raise FalyxError("This is a FalyxError.")
    elif error == "FlowSignal":
        raise FlowSignal("Flow signal triggered.")
    else:
        raise asyncio.CancelledError("An error occurred in the action.")


@pytest.fixture
def flx() -> Falyx:
    sys.argv = ["falyx", "T"]
    flx = Falyx()
    flx.add_command(
        "T",
        "Test",
        action=lambda: "hello",
    )
    flx.add_tldr_example(
        entry_key="T",
        usage="",
        description="This is a TLDR example for the T command.",
    )
    return flx


@pytest.fixture
def flx_with_submenu() -> Falyx:
    flx = Falyx()
    submenu = Falyx("Submenu")
    submenu.add_command(
        "T",
        "Test",
        action=lambda: "hello from submenu",
    )
    submenu.add_tldr_example(
        entry_key="T",
        usage="",
        description="This is a TLDR example for the T command in the submenu.",
    )
    flx.add_submenu(
        "S",
        "Submenu",
        submenu=submenu,
    )
    return flx


@pytest.mark.asyncio
async def test_run_basic(capsys):
    sys.argv = ["falyx", "-h"]
    flx = Falyx()
    with pytest.raises(SystemExit):
        await flx.run()

    captured = capsys.readouterr()
    assert "Show this help menu." in captured.out


@pytest.mark.asyncio
async def test_run_default_to_menu(flx):
    sys.argv = ["falyx", "T"]
    flx.default_to_menu = False

    with pytest.raises(SystemExit):
        await flx.run()

    await flx.run(always_start_menu=True)


@pytest.mark.asyncio
async def test_run_default_to_menu_help(flx):
    sys.argv = ["falyx"]
    flx.default_to_menu = False
    with pytest.raises(SystemExit, match="0"):
        with falyx_console.capture() as capture:
            await flx.run()

    captured = Text.from_ansi(capture.get()).plain
    assert "Show this help menu." in captured


@pytest.mark.asyncio
async def test_run_debug_hooks(flx):
    sys.argv = ["falyx", "--debug-hooks", "T"]

    assert flx.options_manager.get("debug_hooks", namespace_name="root") is False

    with pytest.raises(SystemExit):
        await flx.run()

    assert flx.options_manager.get("debug_hooks", namespace_name="root") is False


@pytest.mark.asyncio
async def test_run_never_prompt(flx):
    sys.argv = ["falyx", "--never-prompt", "T"]

    assert flx.options_manager.get("never_prompt", namespace_name="root") is False

    with pytest.raises(SystemExit):
        await flx.run()

    assert flx.options_manager.get("debug_hooks", namespace_name="root") is False
    assert flx.options_manager.get("never_prompt", namespace_name="root") is False


@pytest.mark.asyncio
async def test_run_bad_args(flx):
    sys.argv = ["falyx", "T", "--unknown-arg"]

    with pytest.raises(SystemExit, match="2"):
        await flx.run()


@pytest.mark.asyncio
async def test_run_help(flx):
    sys.argv = ["falyx", "T", "--help"]
    with pytest.raises(SystemExit, match="0"):
        await flx.run()

    sys.argv = ["falyx", "--help"]
    with pytest.raises(SystemExit, match="0"):
        await flx.run()

    sys.argv = ["falyx", "-h"]
    with pytest.raises(SystemExit, match="0"):
        await flx.run()

    sys.argv = ["falyx", "--tldr"]
    with pytest.raises(SystemExit, match="0"):
        await flx.run()

    sys.argv = ["falyx", "-T"]
    with pytest.raises(SystemExit, match="0"):
        await flx.run()


@pytest.mark.asyncio
async def test_run_entry_not_found(flx):
    sys.argv = ["falyx", "UNKNOWN_COMMAND"]

    with pytest.raises(SystemExit, match="2"):
        await flx.run()


@pytest.mark.asyncio
async def test_run_test_exceptions(flx):
    flx.add_command(
        "E",
        "Throw Error",
        action=throw_error_action,
    )

    sys.argv = ["falyx", "E", "ValueError"]
    with pytest.raises(SystemExit, match="1"):
        await flx.run()

    sys.argv = ["falyx", "E", "QuitSignal"]
    with pytest.raises(SystemExit, match="130"):
        await flx.run()

    sys.argv = ["falyx", "E", "BackSignal"]
    with pytest.raises(SystemExit, match="1"):
        await flx.run()

    sys.argv = ["falyx", "E", "CancelSignal"]
    with pytest.raises(SystemExit, match="1"):
        await flx.run()

    sys.argv = ["falyx", "E", "HelpSignal"]
    with pytest.raises(SystemExit, match="1"):
        await flx.run()

    sys.argv = ["falyx", "E", "FlowSignal"]
    with pytest.raises(SystemExit, match="1"):
        await flx.run()

    sys.argv = ["falyx", "--verbose", "E", "FalyxError"]
    with pytest.raises(SystemExit, match="1"):
        await flx.run()

    sys.argv = ["falyx", "E", "UnknownError"]
    with pytest.raises(SystemExit, match="1"):
        await flx.run()


@pytest.mark.asyncio
async def test_run_no_args(flx):
    sys.argv = ["falyx"]

    with pytest.raises(SystemExit, match="0"):
        await flx.run()


@pytest.mark.asyncio
async def test_run_submenu(flx_with_submenu):
    sys.argv = ["falyx", "S", "T"]

    with pytest.raises(SystemExit, match="0"):
        await flx_with_submenu.run()


@pytest.mark.asyncio
async def test_run_submenu_help(flx_with_submenu):
    sys.argv = ["falyx", "S", "--help"]

    with pytest.raises(SystemExit, match="0"):
        await flx_with_submenu.run()


@pytest.mark.asyncio
async def test_run_submenu_tldr(flx_with_submenu):
    sys.argv = ["falyx", "S", "--tldr"]

    with pytest.raises(SystemExit, match="0"):
        await flx_with_submenu.run()


@pytest.mark.asyncio
async def test_run_preview(flx):
    sys.argv = ["falyx", "preview", "T"]

    with pytest.raises(SystemExit, match="0"):
        with falyx_console.capture() as capture:
            await flx.run()

    captured = Text.from_ansi(capture.get()).plain
    assert "Command: 'T'" in captured
    assert "Would call: <lambda>(args=(), kwargs={})" in captured


@pytest.mark.asyncio
async def test_run_applies_root_defaults_without_overwriting_existing_root_values():
    child = Falyx(program="child")
    child.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    child.options_manager.set("verbose", True, "root")

    root = Falyx(program="root")
    root.add_submenu(
        key="C",
        description="Child Menu",
        submenu=child,
    )

    async def fake_dispatch_route(*, route, args, kwargs, execution_args, **_):
        assert route.namespace is child
        assert route.root_overrides == {}
        assert route.root_defaults["verbose"] is False
        assert route.namespace.options_manager.get("verbose", False, "root") is True

    root._dispatch_route = fake_dispatch_route

    sys.argv = ["falyx", "C", "D"]
    with pytest.raises(SystemExit) as excinfo:
        await root.run()

    assert excinfo.value.code == 0

    assert child.options_manager.get("verbose", False, "root") is True


@pytest.mark.asyncio
async def test_run_applies_root_overrides_temporarily_and_restores_root_namespace():
    child = Falyx(program="child")
    child.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    child.options_manager.set("verbose", False, "root")

    root = Falyx(program="root")
    root.add_submenu(
        key="C",
        description="Child Menu",
        submenu=child,
    )

    seen_during_dispatch = {}

    async def fake_dispatch_route(*, route, args, kwargs, execution_args, **_):
        seen_during_dispatch["verbose"] = route.namespace.options_manager.get(
            "verbose", False, "root"
        )
        assert route.namespace is child
        assert route.root_overrides == {"verbose": True}
        assert seen_during_dispatch["verbose"] is True

    root._dispatch_route = fake_dispatch_route

    sys.argv = ["falyx", "--verbose", "C", "D"]
    with pytest.raises(SystemExit) as excinfo:
        await root.run()

    assert excinfo.value.code == 0
    assert seen_during_dispatch["verbose"] is True

    assert child.options_manager.get("verbose", False, "root") is False
