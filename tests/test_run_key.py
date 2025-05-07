import pytest

from falyx import Action, Falyx


@pytest.mark.asyncio
async def test_run_key():
    """Test if Falyx can run in run key mode."""
    falyx = Falyx("Run Key Test")

    # Add a simple command
    falyx.add_command(
        key="T",
        description="Test Command",
        action=lambda: "Hello, World!",
    )

    # Run the CLI
    result = await falyx.run_key("T")
    assert result == "Hello, World!"


@pytest.mark.asyncio
async def test_run_key_recover():
    """Test if Falyx can recover from a failure in run key mode."""
    falyx = Falyx("Run Key Recovery Test")

    state = {"count": 0}

    async def flaky():
        if not state["count"]:
            state["count"] += 1
            raise RuntimeError("Random failure!")
        return "ok"

    # Add a command that raises an exception
    falyx.add_command(
        key="E",
        description="Error Command",
        action=Action("flaky", flaky),
        retry=True,
    )

    result = await falyx.run_key("E")
    assert result == "ok"
