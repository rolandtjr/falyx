import pytest

from falyx import Falyx


@pytest.mark.asyncio
async def test_help_command(capsys):
    flx = Falyx()
    await flx.run_key("H")

    captured = capsys.readouterr()
    assert "Show this help menu" in captured.out


@pytest.mark.asyncio
async def test_help_command_with_new_command(capsys):
    flx = Falyx()

    async def new_command(falyx: Falyx):
        pass

    flx.add_command(
        "N",
        "New Command",
        new_command,
        aliases=["TEST"],
        help_text="This is a new command.",
    )
    await flx.run_key("H")

    captured = capsys.readouterr()
    assert "This is a new command." in captured.out
    assert "TEST" in captured.out and "N" in captured.out


@pytest.mark.asyncio
async def test_render_help(capsys):
    flx = Falyx()

    async def sample_command(falyx: Falyx):
        pass

    flx.add_command(
        "S",
        "Sample Command",
        sample_command,
        aliases=["SC"],
        help_text="This is a sample command.",
    )
    await flx._render_help()

    captured = capsys.readouterr()
    assert "This is a sample command." in captured.out
    assert "SC" in captured.out and "S" in captured.out


@pytest.mark.asyncio
async def test_help_command_by_tag(capsys):
    flx = Falyx()

    async def tagged_command(falyx: Falyx):
        pass

    flx.add_command(
        "T",
        "Tagged Command",
        tagged_command,
        tags=["tag1"],
        help_text="This command is tagged.",
    )
    await flx.run_key("H", args=("tag1",))

    captured = capsys.readouterr()
    assert "tag1" in captured.out
    assert "This command is tagged." in captured.out
    assert "HELP" not in captured.out


@pytest.mark.asyncio
async def test_help_command_empty_tags(capsys):
    flx = Falyx()

    async def untagged_command(falyx: Falyx):
        pass

    flx.add_command(
        "U", "Untagged Command", untagged_command, help_text="This command has no tags."
    )
    await flx.run_key("H", args=("nonexistent_tag",))

    captured = capsys.readouterr()
    print(captured.out)
    assert "nonexistent_tag" in captured.out
    assert "Nothing to show here" in captured.out
