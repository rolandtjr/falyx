from unittest.mock import AsyncMock

import pytest

from falyx.action import Action
from falyx.command import Command
from falyx.options_manager import OptionsManager
from falyx.prompt_utils import should_prompt_user
from falyx.signals import CancelSignal


def _make_options() -> OptionsManager:
    options = OptionsManager()
    options.from_mapping({}, "root")
    options.from_mapping({}, "execution")
    return options


@pytest.mark.asyncio
async def test_command_handle_prompt_respects_action_local_never_prompt(monkeypatch):
    options = _make_options()

    command = Command.build(
        key="D",
        description="Deploy",
        action=Action("deploy-action", lambda: "ok", never_prompt=True),
        confirm=True,
        preview_before_confirm=True,
        options_manager=options,
    )

    calls = {
        "preview": 0,
        "confirm": 0,
        "should_prompt": 0,
        "action_never_prompt": None,
    }

    async def fake_preview(self):
        calls["preview"] += 1

    async def fake_confirm(*args, **kwargs):
        calls["confirm"] += 1
        return True

    def fake_should_prompt_user(*, confirm, options, action_never_prompt=None, **kwargs):
        calls["should_prompt"] += 1
        calls["action_never_prompt"] = action_never_prompt
        return False

    monkeypatch.setattr(Command, "preview", fake_preview)
    monkeypatch.setattr("falyx.command.confirm_async", fake_confirm)
    monkeypatch.setattr("falyx.command.should_prompt_user", fake_should_prompt_user)

    await command._handle_prompt_user()

    assert calls["should_prompt"] == 1
    assert calls["action_never_prompt"] is True
    assert calls["preview"] == 0
    assert calls["confirm"] == 0


def test_should_prompt_user_precedence_execution_over_root():
    options = _make_options()
    options.set("force_confirm", True, "root")
    options.set("skip_confirm", True, "execution")

    assert should_prompt_user(confirm=False, options=options) is False

    options = _make_options()
    options.set("never_prompt", False, "root")
    options.set("force_confirm", True, "execution")

    assert should_prompt_user(confirm=False, options=options) is True


@pytest.mark.asyncio
async def test_command_local_never_prompt_overrides_root_prompt_behavior(monkeypatch):
    options = _make_options()
    options.set("force_confirm", True, "root")

    command = Command.build(
        key="D",
        description="Deploy",
        action=Action("deploy-action", lambda: "ok", never_prompt=True),
        confirm=False,
        preview_before_confirm=True,
        options_manager=options,
    )

    calls = {
        "preview": 0,
        "confirm": 0,
    }

    async def fake_preview(self):
        calls["preview"] += 1

    async def fake_confirm(*args, **kwargs):
        calls["confirm"] += 1
        return True

    monkeypatch.setattr(Command, "preview", fake_preview)
    monkeypatch.setattr("falyx.command.confirm_async", fake_confirm)

    await command._handle_prompt_user()

    assert calls["preview"] == 0
    assert calls["confirm"] == 0


@pytest.mark.asyncio
async def test_command_call_invokes_handle_prompt_user(monkeypatch):
    options = OptionsManager()
    options.from_mapping({}, "root")
    options.from_mapping({}, "execution")

    command = Command.build(
        key="D",
        description="Deploy",
        action=Action("deploy-action", lambda: "ok"),
        confirm=True,
        options_manager=options,
    )

    mocked_handle_prompt = AsyncMock()
    monkeypatch.setattr(command, "_handle_prompt_user", mocked_handle_prompt)

    result = await command()

    mocked_handle_prompt.assert_awaited_once()
    assert result == "ok"


@pytest.mark.asyncio
async def test_command_call_invokes_handle_prompt_user_before_action(monkeypatch) -> None:
    trace: list[str] = []

    async def run_action():
        trace.append("action")
        return "ok"

    options = OptionsManager()
    options.from_mapping({}, "root")
    options.from_mapping({}, "execution")

    command = Command.build(
        key="D",
        description="Deploy",
        action=Action("deploy-action", run_action),
        confirm=True,
        options_manager=options,
    )

    async def fake_handle_prompt_user():
        trace.append("prompt")

    monkeypatch.setattr(command, "_handle_prompt_user", fake_handle_prompt_user)

    result = await command()

    assert result == "ok"
    assert trace == ["prompt", "action"]


@pytest.mark.asyncio
async def test_command_call_cancels_before_action_when_handle_prompt_user_raises(
    monkeypatch,
):
    trace: list[str] = []

    async def run_action():
        trace.append("action")
        return "ok"

    options = OptionsManager()
    options.from_mapping({}, "root")
    options.from_mapping({}, "execution")

    command = Command.build(
        key="D",
        description="Deploy",
        action=Action("deploy-action", run_action),
        confirm=True,
        options_manager=options,
    )

    async def fake_handle_prompt_user():
        trace.append("prompt")
        raise CancelSignal("cancelled during confirmation")

    monkeypatch.setattr(command, "_handle_prompt_user", fake_handle_prompt_user)

    with pytest.raises(CancelSignal, match="cancelled during confirmation"):
        await command()

    assert trace == ["prompt"]
