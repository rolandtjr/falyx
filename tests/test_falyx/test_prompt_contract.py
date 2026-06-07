from falyx.action import Action
from falyx.command import Command


async def test_action_local_never_prompt_bypasses_command_confirmation(monkeypatch):
    called = False

    async def fake_confirm(*args, **kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr("falyx.command.confirm_async", fake_confirm)

    action = Action("Do Thing", lambda: "ok", never_prompt=True)
    command = Command.build("D", "Do Thing", action=action, confirm=True)

    result = await command()

    assert result == "ok"
    assert called is False
