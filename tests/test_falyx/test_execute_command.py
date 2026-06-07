import pytest

from falyx import Falyx
from falyx.action import Action
from falyx.command_runner import CommandRunner
from falyx.parser import CommandArgumentParser


@pytest.mark.asyncio
async def test_execute_command():
    """Test if Falyx can run in run key mode."""
    falyx = Falyx("Run Key Test")

    falyx.add_command(
        key="T",
        description="Test Command",
        action=lambda: "Hello, World!",
    )

    result = await falyx.execute_command("T")
    assert result == "Hello, World!"


@pytest.mark.asyncio
async def test_execute_command_accepts_alias():
    """Falyx.execute_command should resolve command aliases."""
    falyx = Falyx("Alias Test")

    falyx.add_command(
        key="T",
        description="Test Command",
        action=lambda: "Hello, Alias!",
        aliases=["test"],
    )

    result = await falyx.execute_command("test")
    assert result == "Hello, Alias!"


@pytest.mark.asyncio
async def test_execute_command_recover():
    """Test if Falyx can recover from a failure in run key mode."""
    falyx = Falyx("Run Key Recovery Test")

    state = {"count": 0}

    async def flaky():
        if not state["count"]:
            state["count"] += 1
            raise RuntimeError("Random failure!")
        return "ok"

    falyx.add_command(
        key="E",
        description="Error Command",
        action=Action("flaky", flaky),
        retry=True,
    )

    result = await falyx.execute_command("E")
    assert result == "ok"


@pytest.mark.asyncio
async def test_execute_command_with_argument_parsing():
    """Falyx.execute_command should parse command-local arguments before execution."""
    falyx = Falyx("Argument Parsing Test")

    falyx.add_command(
        key="G",
        description="Greet",
        action=lambda name: f"hello {name}",
    )

    result = await falyx.execute_command("G Roland")
    assert result == "hello Roland"


@pytest.mark.asyncio
async def test_command_runner_and_falyx_execute_same_command_with_same_result():
    """CommandRunner and Falyx should produce the same result for equivalent input."""
    falyx = Falyx("Parity Test")

    command = falyx.add_command(
        key="G",
        description="Greet",
        action=lambda name: f"hello {name}",
        aliases=["greet"],
    )

    runner = CommandRunner.from_command(command)

    falyx_result = await falyx.execute_command("G Roland")
    runner_result = await runner.run(["Roland"])

    assert falyx_result == "hello Roland"
    assert runner_result == "hello Roland"
    assert falyx_result == runner_result


@pytest.mark.asyncio
async def test_command_runner_from_command_clones_and_preserves_parity():
    """Runner parity should hold even though from_command binds a clone."""
    falyx = Falyx("Clone Parity Test")

    parser = CommandArgumentParser()
    parser.add_argument("x", type=int)
    parser.add_argument("y", type=int)

    command = falyx.add_command(
        key="A",
        description="Add",
        action=lambda x, y: x + y,
        arg_parser=parser,
    )

    runner = CommandRunner.from_command(command)

    result_from_falyx = await falyx.execute_command("A 2 3")
    result_from_runner = await runner.run(["2", "3"])

    assert result_from_falyx == 5
    assert result_from_runner == 5
    assert runner.command is not command
