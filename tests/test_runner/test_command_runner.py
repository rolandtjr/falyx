import asyncio
import sys

import pytest
from rich.console import Console
from rich.text import Text

from falyx.action import Action
from falyx.command import Command
from falyx.command_runner import CommandRunner
from falyx.console import console as falyx_console
from falyx.exceptions import CommandArgumentError, FalyxError, NotAFalyxError
from falyx.hook_manager import HookManager, HookType
from falyx.options_manager import OptionsManager
from falyx.signals import BackSignal, CancelSignal, HelpSignal, QuitSignal


async def ok_action(*args, **kwargs):
    falyx_console.print("Action executed with args:", args, "and kwargs:", kwargs)
    return "ok"


async def failing_action(*args, **kwargs):
    raise RuntimeError("boom")


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
    else:
        raise asyncio.CancelledError("An error occurred in the action.")


@pytest.fixture
def command_throwing_error():
    command = Command(
        key="E",
        description="Error Command",
        action=Action("throw_error", throw_error_action),
        execution_options=["retry"],
    )
    return command


@pytest.fixture
def command_with_parser():
    command = Command(
        key="T",
        description="Test Command",
        action=ok_action,
    )
    command.arg_parser.add_argument("--foo", type=int, help="A business argument.")
    return command


@pytest.fixture
def command_with_no_parser():
    command = Command(
        key="T",
        description="Test Command",
        action=ok_action,
        execution_options=["summary"],
    )
    command.arg_parser = None
    return command


@pytest.fixture
def command_with_custom_parser():
    def parse_args_split(arg_list):
        return (arg_list,), {}, {"custom_execution_arg": True}

    command = Command(
        key="T",
        description="Test Command",
        action=ok_action,
        execution_options=["summary"],
    )
    command.custom_parser = parse_args_split
    return command


@pytest.fixture
def command_with_failing_action():
    command = Command(
        key="T",
        description="Test Command",
        action=failing_action,
        execution_options=["summary", "retry"],
    )
    command.arg_parser.add_argument("--foo", type=int, help="A business argument.")
    return command


@pytest.fixture
def command_build_with_all_execution_options():
    return Command.build(
        key="T",
        description="Test Command",
        action=ok_action,
        execution_options=["summary", "retry", "confirm"],
    )


@pytest.fixture
def console():
    return Console(record=True)


@pytest.mark.asyncio
async def test_command_runner_initialization(
    command_with_parser,
    command_with_no_parser,
    command_with_custom_parser,
):
    runner = CommandRunner(command_with_parser)
    assert runner.command == command_with_parser
    assert isinstance(runner.options, OptionsManager)
    assert isinstance(runner.runner_hooks, HookManager)
    assert runner.console == falyx_console
    assert runner.command.options_manager == runner.options
    assert runner.command.arg_parser.options_manager == runner.options
    assert runner.command.options_manager == runner.options
    assert runner.executor.options == runner.options
    assert runner.executor.hooks == runner.runner_hooks
    assert runner.executor.console == runner.console
    assert runner.options.get("summary", namespace_name="execution") is None

    runner_no_parser = CommandRunner(command_with_no_parser)
    assert runner_no_parser.command == command_with_no_parser
    assert runner_no_parser.command.arg_parser is None

    CommandRunner(command_with_no_parser)
    with pytest.raises(
        NotAFalyxError,
        match="Command has no parser configured. Provide a custom_parser or CommandArgumentParser.",
    ):
        await runner_no_parser.run("--summary")

    runner_custom_parser = CommandRunner(command_with_custom_parser)
    assert runner_custom_parser.command == command_with_custom_parser
    assert runner_custom_parser.command.custom_parser is not None


def test_command_runner_initialization_with_custom_options(command_with_parser):
    custom_options = OptionsManager([("default", {"summary": True})])
    runner = CommandRunner(command_with_parser, options=custom_options)
    assert runner.options == custom_options
    assert runner.options.get("summary", namespace_name="default") is True
    assert runner.command.options_manager == runner.options
    assert runner.command.arg_parser.options_manager == runner.options
    assert runner.command.options_manager == runner.options


def test_command_runner_initialization_with_custom_console(command_with_parser):
    custom_console = Console()
    runner = CommandRunner(command_with_parser, console=custom_console)
    assert runner.console == custom_console
    assert runner.executor.console == custom_console


def test_command_runner_initialization_with_custom_hooks(command_with_parser):
    custom_hooks = HookManager()
    custom_hooks.register("before", lambda context: print("Before hook"))
    runner = CommandRunner(command_with_parser, runner_hooks=custom_hooks)
    assert runner.runner_hooks == custom_hooks
    assert runner.executor.hooks == custom_hooks
    assert runner.runner_hooks._hooks[HookType.BEFORE]


def test_command_runner_initialization_with_all_bad_components(command_with_parser):
    custom_options = "Not an OptionsManager"
    custom_console = 23456
    custom_hooks = "Not a HookManager"

    with pytest.raises(
        NotAFalyxError, match="options must be an instance of OptionsManager"
    ):
        CommandRunner(
            command_with_parser,
            options=custom_options,
        )

    with pytest.raises(
        NotAFalyxError, match="console must be an instance of rich.Console"
    ):
        CommandRunner(
            command_with_parser,
            console=custom_console,
        )

    with pytest.raises(NotAFalyxError, match="hooks must be an instance of HookManager"):
        CommandRunner(
            command_with_parser,
            runner_hooks=custom_hooks,
        )


@pytest.mark.asyncio
async def test_command_runner_run(command_with_parser):
    runner = CommandRunner(command_with_parser)
    with falyx_console.capture() as capture:
        result = await runner.run("--foo 42")
    captured = Text.from_ansi(capture.get()).plain
    assert result == "ok"
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "{'foo': 42}" in captured

    falyx_console.clear()
    with falyx_console.capture() as capture:
        result = await runner.run(["--foo", "123"])
    captured = Text.from_ansi(capture.get()).plain
    assert result == "ok"
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "{'foo': 123}" in captured


@pytest.mark.asyncio
async def test_command_runner_run_with_failing_action(command_with_failing_action):
    runner = CommandRunner(command_with_failing_action)
    with pytest.raises(RuntimeError, match="boom"):
        await runner.run("--foo 42")

    with pytest.raises(FalyxError, match="boom"):
        await runner.run("--foo 42", wrap_errors=True)

    assert await runner.run("--foo 42", wrap_errors=False, raise_on_error=False) is None


@pytest.mark.asyncio
async def test_command_runner_debug_statement(command_with_parser, caplog):
    caplog.set_level("DEBUG")
    runner = CommandRunner(command_with_parser)
    await runner.run("--foo 42")
    assert (
        "Executing command 'Test Command' with args=(), kwargs={'foo': 42}" in caplog.text
    )


@pytest.mark.asyncio
async def test_command_runner_run_with_retries_non_action(
    command_with_failing_action, caplog
):
    runner = CommandRunner(command_with_failing_action)
    with pytest.raises(RuntimeError, match="boom"):
        await runner.run("--foo 42 --retries 2")

    assert "Retry requested, but action is not an Action instance." in caplog.text


@pytest.mark.asyncio
async def test_command_runner_run_with_retries_with_action(
    command_throwing_error, caplog
):
    runner = CommandRunner(command_throwing_error)
    with pytest.raises(asyncio.CancelledError, match="An error occurred in the action."):
        await runner.run("Other")

    with pytest.raises(ValueError, match="This is a ValueError."):
        await runner.run("ValueError --retries 2")

    assert "[throw_error] Retry attempt 1/2 failed due to 'ValueError'." in caplog.text
    assert "[throw_error] Retry attempt 2/2 failed due to 'ValueError'." in caplog.text
    assert "[throw_error] All 2 retries failed." in caplog.text


@pytest.mark.asyncio
async def test_command_runner_run_from_command_build_with_all_execution_options(
    command_build_with_all_execution_options,
):
    runner = CommandRunner.from_command(command_build_with_all_execution_options)
    with falyx_console.capture() as capture:
        result = await runner.run("--summary")
    captured = Text.from_ansi(capture.get()).plain
    assert result == "ok"
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "Execution History" in captured

    with falyx_console.capture() as capture:
        result = await runner.run("--summary", summary_last_result=True)
    captured = Text.from_ansi(capture.get()).plain
    assert result == "ok"
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "Command(key='T', description='Test Command' action=" in captured
    assert "ok" in captured

    with falyx_console.capture() as capture:
        result = await runner.run("--summary", summary_last_result=False)
    captured = Text.from_ansi(capture.get()).plain
    assert result == "ok"
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "Execution History" in captured


@pytest.mark.asyncio
async def test_command_runner_from_command_bad_command():
    with pytest.raises(NotAFalyxError, match="command must be an instance of Command"):
        CommandRunner.from_command("Not a Command")

    with pytest.raises(
        NotAFalyxError, match="runner_hooks must be an instance of HookManager"
    ):
        CommandRunner.from_command(
            Command(
                key="T",
                description="Test Command",
                action=ok_action,
            ),
            runner_hooks="Not a HookManager",
        )


@pytest.mark.asyncio
async def test_command_runner_build():
    runner = CommandRunner.build(
        key="T",
        description="Test Command",
        action=ok_action,
        execution_options=["summary", "retry"],
    )
    assert isinstance(runner, CommandRunner)
    with falyx_console.capture() as capture:
        result = await runner.run("--summary --retries 2")
    captured = Text.from_ansi(capture.get()).plain
    assert result == "ok"
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "Execution History" in captured


@pytest.mark.asyncio
async def test_command_runner_build_with_bad_execution_options():
    with pytest.raises(
        ValueError,
        match="Invalid ExecutionOption: 'invalid_option'. Must be one of:",
    ):
        CommandRunner.build(
            key="T",
            description="Test Command",
            action=ok_action,
            execution_options=["summary", "invalid_option"],
        )


@pytest.mark.asyncio
async def test_command_runner_build_with_bad_runner_hooks():
    with pytest.raises(
        NotAFalyxError, match="runner_hooks must be an instance of HookManager"
    ):
        CommandRunner.build(
            key="T",
            description="Test Command",
            action=ok_action,
            runner_hooks="Not a HookManager",
        )


@pytest.mark.asyncio
async def test_command_runner_uses_sys_argv(command_with_parser, monkeypatch):
    runner = CommandRunner(command_with_parser)
    test_args = ["program_name", "--foo", "42"]
    monkeypatch.setattr(sys, "argv", test_args)
    with falyx_console.capture() as capture:
        result = await runner.run()
    captured = Text.from_ansi(capture.get()).plain
    assert result == "ok"
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "{'foo': 42}" in captured


@pytest.mark.asyncio
async def test_command_runner_cli(command_with_parser):
    runner = CommandRunner(command_with_parser)
    with falyx_console.capture() as capture:
        await runner.cli("--foo 42")
    captured = Text.from_ansi(capture.get()).plain
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "{'foo': 42}" in captured


@pytest.mark.asyncio
async def test_command_runnner_run_propogates_exeptions(command_throwing_error):
    runner = CommandRunner(command_throwing_error)

    with pytest.raises(QuitSignal, match="Quit signal triggered."):
        await runner.run("QuitSignal")

    with pytest.raises(BackSignal, match="Back signal triggered."):
        await runner.run("BackSignal")

    with pytest.raises(CancelSignal, match="Cancel signal triggered."):
        await runner.run("CancelSignal")

    with pytest.raises(ValueError, match="This is a ValueError."):
        await runner.run("ValueError")

    with pytest.raises(HelpSignal, match="Help signal triggered."):
        await runner.run("HelpSignal")

    with pytest.raises(asyncio.CancelledError, match="An error occurred in the action."):
        await runner.run("Other")

    with pytest.raises(
        CommandArgumentError,
        match=r"\[E\] Failed to parse arguments: No closing quotation",
    ):
        await runner.run("Mismatched'")


@pytest.mark.asyncio
async def test_command_runner_cli_with_failing_action(command_with_failing_action):
    runner = CommandRunner(command_with_failing_action)
    with pytest.raises(SystemExit, match="1"):
        await runner.cli("--foo 42")

    with pytest.raises(SystemExit, match="2"):
        await runner.cli("--foo 42 --bar 123")

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="0"):
            await runner.cli(["--help"])
    captured = Text.from_ansi(capture.get()).plain

    assert "usage: falyx T" in captured
    assert "--foo" in captured
    assert "summary" in captured
    assert "retries" in captured
    assert "A business argument." in captured


@pytest.mark.asyncio
async def test_command_runner_cli_exceptions(command_throwing_error):
    runner = CommandRunner(command_throwing_error)

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="0"):
            await runner.cli(["--help"])
    captured = Text.from_ansi(capture.get()).plain
    assert "falyx E [--help]" in captured
    assert "usage:" in captured
    assert "positional:" in captured
    assert "options:" in captured
    assert "❌" not in captured

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="2"):
            await runner.cli(["--not-an-arg"])
    captured = Text.from_ansi(capture.get()).plain
    assert "falyx E [--help]" in captured
    assert "usage:" in captured
    assert "positional:" in captured
    assert "options:" in captured
    assert "❌" in captured
    falyx_console.clear()

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["FalyxError"])
    captured = Text.from_ansi(capture.get()).plain
    assert "This is a FalyxError." in captured
    assert "❌ Error:" in captured
    falyx_console.clear()

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="130"):
            await runner.cli(["QuitSignal"])
    captured = Text.from_ansi(capture.get()).plain
    assert "❌" not in captured

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["BackSignal"])
    captured = Text.from_ansi(capture.get()).plain
    assert "❌" not in captured

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["CancelSignal"])
    captured = Text.from_ansi(capture.get()).plain
    assert "❌" not in captured

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["Other"])
    captured = Text.from_ansi(capture.get()).plain
    assert "❌" not in captured


@pytest.mark.asyncio
async def test_command_runner_cli_uses_sys_argv(command_with_parser, monkeypatch):
    runner = CommandRunner(command_with_parser)
    test_args = ["program_name", "--foo", "42"]
    monkeypatch.setattr(sys, "argv", test_args)
    with falyx_console.capture() as capture:
        await runner.cli()
    captured = Text.from_ansi(capture.get()).plain
    assert "Action executed with args:" in captured
    assert "and kwargs:" in captured
    assert "{'foo': 42}" in captured
