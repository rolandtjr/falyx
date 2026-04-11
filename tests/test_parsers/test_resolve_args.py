import pytest

from falyx.command import Command
from falyx.exceptions import CommandArgumentError, NotAFalyxError
from falyx.execution_option import ExecutionOption


@pytest.mark.asyncio
async def test_resolve_args_separates_business_and_execution_options():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary", "retry"],
    )
    command.arg_parser.add_argument("--foo", type=int, help="A business argument.")

    args, kwargs, execution_args = await command.resolve_args(
        ["--foo", "42", "--summary", "--retries", "3"]
    )

    assert args == ()
    assert kwargs == {"foo": 42}
    assert execution_args == {
        "summary": True,
        "retries": 3,
        "retry_delay": 0.0,
        "retry_backoff": 0.0,
    }

    args, kwargs, execution_args = await command.arg_parser.parse_args_split(
        ["--foo", "42", "--summary", "--retries", "3"]
    )

    assert args == ()
    assert kwargs == {"foo": 42}
    assert execution_args == {
        "summary": True,
        "retries": 3,
        "retry_delay": 0.0,
        "retry_backoff": 0.0,
    }


@pytest.mark.asyncio
async def test_parse_args_split_with_no_execution_options_returns_empty_execution_args():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
    )
    command.arg_parser.add_argument("--foo", type=int, help="A business argument.")

    args, kwargs, execution_args = await command.arg_parser.parse_args_split(
        ["--foo", "42"]
    )

    assert args == ()
    assert kwargs == {"foo": 42}
    assert execution_args == {}


@pytest.mark.asyncio
async def test_resolve_args_raises_on_conflicting_execution_option():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary"],
    )
    with pytest.raises(
        CommandArgumentError, match="Destination 'summary' is already defined"
    ):
        command.arg_parser.add_argument(
            "--summary", action="store_true", help="A conflicting argument."
        )

    with pytest.raises(
        CommandArgumentError, match="Destination 'summary' is already defined"
    ):
        command.arg_parser.enable_execution_options(frozenset({ExecutionOption.SUMMARY}))


@pytest.mark.asyncio
async def test_resolve_args_mix_of_business_and_execution_options():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["retry"],
    )
    command.arg_parser.add_argument("--summary", type=str, help="A business argument.")

    args, kwargs, execution_args = await command.resolve_args(
        ["--summary", "test", "--retries", "5", "--retry-delay", "2"]
    )

    assert args == ()
    assert kwargs == {"summary": "test"}
    assert execution_args == {"retries": 5, "retry_delay": 2.0, "retry_backoff": 0.0}


@pytest.mark.asyncio
async def test_resolve_args_with_no_arguments():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary"],
    )

    args, kwargs, execution_args = await command.resolve_args([])

    assert args == ()
    assert kwargs == {}
    assert execution_args == {"summary": False}


@pytest.mark.asyncio
async def test_resolve_args_with_confirmation_options():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["confirm"],
    )

    args, kwargs, execution_args = await command.resolve_args(["--confirm"])

    assert args == ()
    assert kwargs == {}
    assert execution_args == {"force_confirm": True, "skip_confirm": False}

    args, kwargs, execution_args = await command.resolve_args(["--skip-confirm"])

    assert args == ()
    assert kwargs == {}
    assert execution_args == {"force_confirm": False, "skip_confirm": True}


@pytest.mark.asyncio
async def test_resolve_args_with_all_execution_options():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary", "retry", "confirm"],
    )

    args, kwargs, execution_args = await command.resolve_args(
        ["--summary", "--retries", "3", "--confirm"]
    )

    assert args == ()
    assert kwargs == {}
    assert execution_args == {
        "summary": True,
        "retries": 3,
        "retry_delay": 0.0,
        "retry_backoff": 0.0,
        "force_confirm": True,
        "skip_confirm": False,
    }


@pytest.mark.asyncio
async def test_resolve_args_with_raw_string_input():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary"],
    )
    command.arg_parser.add_argument("--foo", type=int, help="A business argument.")

    args, kwargs, execution_args = await command.resolve_args("--foo 42 --summary")

    assert args == ()
    assert kwargs == {"foo": 42}
    assert execution_args == {"summary": True}


@pytest.mark.asyncio
async def test_resolve_args_with_no_arg_parser():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary"],
    )
    command.arg_parser = None

    with pytest.raises(
        NotAFalyxError,
        match="Command has no parser configured. Provide a custom_parser or CommandArgumentParser.",
    ):
        await command.resolve_args("--summary")


@pytest.mark.asyncio
async def test_resolve_args_with_custom_parser():
    def parse_args_split(arg_list):
        return (arg_list,), {}, {"custom_execution_arg": True}

    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary"],
    )
    command.custom_parser = parse_args_split

    args, kwargs, execution_args = await command.resolve_args("--summary")

    assert args == (["--summary"],)
    assert kwargs == {}
    assert execution_args == {"custom_execution_arg": True}

    # TODO: is this the right behavior? Should we expect the custom parser to handle non string inputs as well? Does this actually happen?
    args, kwargs, execution_args = await command.resolve_args(2235235)

    assert args == (2235235,)
    assert kwargs == {}
    assert execution_args == {"custom_execution_arg": True}

    with pytest.raises(CommandArgumentError, match="Failed to parse arguments:"):
        args, kwargs, execution_args = await command.resolve_args("unbalanced 'quotes")


@pytest.mark.asyncio
async def test_resolve_args_str_unbalanced_quotes():
    command = Command.build(
        key="T",
        description="Test Command",
        action=lambda: None,
        execution_options=["summary"],
    )
    command.arg_parser.add_argument("--foo", type=str, help="A business argument.")

    with pytest.raises(CommandArgumentError, match="Failed to parse arguments:"):
        await command.resolve_args("--foo 'unbalanced quotes")
