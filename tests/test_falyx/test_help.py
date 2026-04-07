import pytest
from rich.text import Text

from falyx import Falyx
from falyx.console import console


@pytest.mark.asyncio
async def test_help_command(capsys):
    flx = Falyx()
    assert flx.help_command.arg_parser.aliases[0] == "HELP"
    assert flx.help_command.arg_parser.command_key == "H"
    await flx.execute_command("H")

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
    await flx.execute_command("H")

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
    await flx.execute_command("H -t tag1")

    captured = capsys.readouterr()
    print(captured.out)
    text = Text.from_ansi(captured.out)
    assert "tag1" in text.plain
    assert "This command is tagged." in text.plain
    assert "HELP" not in text.plain


@pytest.mark.asyncio
async def test_help_command_empty_tags(capsys):
    flx = Falyx()

    async def untagged_command(falyx: Falyx):
        pass

    flx.add_command(
        "U", "Untagged Command", untagged_command, help_text="This command has no tags."
    )
    await flx.execute_command("H nonexistent_tag")

    captured = capsys.readouterr()
    text = Text.from_ansi(captured.out)
    assert "Unexpected positional argument: nonexistent_tag" in text.plain
