import asyncio
import logging
import sys

import pytest
from rich.console import Console
from rich.text import Text

from falyx import Falyx
from falyx.action import Action
from falyx.command import Command
from falyx.command_runner import CommandRunner
from falyx.console import console as falyx_console
from falyx.console import error_console
from falyx.exceptions import (
    CommandArgumentError,
    FalyxError,
    InvalidHookError,
    NotAFalyxError,
)
from falyx.hook_manager import HookManager, HookType
from falyx.options_manager import OptionsManager
from falyx.parser import CommandArgumentParser
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
    runner = CommandRunner(command_with_parser, program="test_program")
    assert runner.command == command_with_parser
    assert runner.program == "test_program"
    assert runner.command.arg_parser.program == "test_program"
    assert isinstance(runner.options_manager, OptionsManager)
    assert isinstance(runner.runner_hooks, HookManager)
    assert runner.console == falyx_console
    assert runner.command.options_manager == runner.options_manager
    assert runner.command.arg_parser.options_manager == runner.options_manager
    assert runner.command.options_manager == runner.options_manager
    assert runner.executor.options_manager == runner.options_manager
    assert runner.executor.hooks == runner.runner_hooks
    assert runner.options_manager.get("summary", namespace_name="execution") is None

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
    runner = CommandRunner(command_with_parser, options_manager=custom_options)
    assert runner.options_manager == custom_options
    assert runner.options_manager.get("summary", namespace_name="default") is True
    assert runner.command.options_manager == runner.options_manager
    assert runner.command.arg_parser.options_manager == runner.options_manager
    assert runner.command.options_manager == runner.options_manager


def test_command_runner_initialization_with_custom_console(command_with_parser):
    custom_console = Console()
    runner = CommandRunner(command_with_parser, console=custom_console)
    assert runner.console == custom_console


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
        NotAFalyxError, match="options_manager must be an instance of OptionsManager"
    ):
        CommandRunner(
            command_with_parser,
            options_manager=custom_options,
        )

    with pytest.raises(
        NotAFalyxError, match="console must be an instance of rich.Console"
    ):
        CommandRunner(
            command_with_parser,
            console=custom_console,
        )

    with pytest.raises(
        InvalidHookError, match="hooks must be an instance of HookManager"
    ):
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


@pytest.mark.asyncio
async def test_command_runner_debug_statement(command_with_parser, caplog):
    logging.getLogger("falyx").setLevel(logging.DEBUG)
    runner = CommandRunner(command_with_parser)
    await runner.run("--foo 42")
    print(command_with_parser.get_option("verbose", namespace_name="root"))
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
async def test_command_runner_run_with_retries_delay_with_action(
    command_throwing_error, caplog
):
    runner = CommandRunner(command_throwing_error)
    with pytest.raises(asyncio.CancelledError, match="An error occurred in the action."):
        await runner.run("Other")

    with pytest.raises(ValueError, match="This is a ValueError."):
        await runner.run("ValueError --retries 2 --retry-delay 1.0 --retry-backoff 2.0")

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
        InvalidHookError, match="runner_hooks must be an instance of HookManager"
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
        InvalidHookError, match="runner_hooks must be an instance of HookManager"
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

    assert "usage: falyx" in captured
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
    assert "falyx [--help]" in captured
    assert "usage:" in captured
    assert "positional:" in captured
    assert "options:" in captured

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="2"):
            await runner.cli(["--not-an-arg"])
    captured = Text.from_ansi(capture.get()).plain
    assert "falyx [--help]" in captured
    assert "usage:" in captured
    assert "positional:" in captured
    assert "options:" in captured
    falyx_console.clear()

    with error_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["FalyxError"])
    captured = Text.from_ansi(capture.get()).plain
    assert "This is a FalyxError." in captured
    assert "error:" in captured
    falyx_console.clear()

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="130"):
            await runner.cli(["QuitSignal"])
    captured = Text.from_ansi(capture.get()).plain

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["BackSignal"])
    captured = Text.from_ansi(capture.get()).plain

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["CancelSignal"])
    captured = Text.from_ansi(capture.get()).plain

    with falyx_console.capture() as capture:
        with pytest.raises(SystemExit, match="1"):
            await runner.cli(["Other"])
    captured = Text.from_ansi(capture.get()).plain


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


@pytest.mark.asyncio
async def test_command_runner_run_error(command_with_parser):
    runner = CommandRunner(command_with_parser)
    with pytest.raises(FalyxError, match="requires either"):
        await runner.run(["--foo", "42"], raise_on_error=False, wrap_errors=False)
    await runner.run(["--foo", "42"], raise_on_error=False, wrap_errors=True)
    await runner.run(["--foo", "42"], raise_on_error=True, wrap_errors=False)


def test_command_runner_from_command_reuses_custom_options_manager_and_seeds_missing_namespaces():
    flx = Falyx(program="source")
    original = flx.add_command(
        key="D",
        description="Deploy",
        action=lambda: "ok",
    )

    custom_options = OptionsManager([("default", {"summary": True})])

    runner = CommandRunner.from_command(
        original,
        options_manager=custom_options,
    )

    assert runner.command is not original
    assert runner.options_manager is custom_options
    assert runner.command.options_manager is custom_options

    assert runner.options_manager.get("summary", namespace_name="default") is True

    assert runner.options_manager.get_namespace("root") == {}
    assert runner.options_manager.get_namespace("execution") == {}

    assert original.options_manager is flx.options_manager
    assert original.options_manager is not custom_options


@pytest.mark.asyncio
async def test_command_runner_root_options_affect_cloned_command_without_mutating_original(
    monkeypatch,
):
    flx = Falyx(program="source")
    original = flx.add_command(
        key="D",
        description="Deploy",
        action=Action("deploy-action", lambda: "ok"),
        confirm=True,
    )

    original.options_manager.set("never_prompt", False, "root")
    original.options_manager.set("verbose", False, "root")

    runner_options = OptionsManager()
    runner_options.from_mapping({}, "root")
    runner_options.from_mapping({}, "execution")
    runner_options.set("never_prompt", True, "root")
    runner_options.set("verbose", True, "root")

    runner = CommandRunner.from_command(
        original,
        options_manager=runner_options,
    )

    calls = {"preview": 0, "confirm": 0}

    async def fake_preview(self):
        calls["preview"] += 1

    async def fake_confirm(*args, **kwargs):
        calls["confirm"] += 1
        return True

    monkeypatch.setattr(Command, "preview", fake_preview)
    monkeypatch.setattr("falyx.command.confirm_async", fake_confirm)

    result = await runner.run([])

    assert result == "ok"

    assert calls["preview"] == 0
    assert calls["confirm"] == 0

    assert runner.command.get_option("never_prompt", namespace_name="root") is True
    assert runner.command.get_option("verbose", namespace_name="root") is True

    assert runner.command.action.get_option("verbose", namespace_name="root") is True
    assert runner.command.action.never_prompt is True

    assert original.get_option("never_prompt", namespace_name="root") is False
    assert original.get_option("verbose", namespace_name="root") is False
    assert original.options_manager is flx.options_manager
    assert original.options_manager is not runner.options_manager


@pytest.mark.asyncio
async def test_command_runner_from_command_with_custom_options_preserves_parity_and_isolation():
    falyx = Falyx("Custom Options Parity Test")

    def add(x: int, y: int) -> int:
        return x + y

    command = falyx.add_command(
        key="A",
        description="Add",
        action=add,
    )

    custom_options = OptionsManager([("default", {"summary": True})])

    runner = CommandRunner.from_command(
        command,
        options_manager=custom_options,
    )

    falyx_result = await falyx.execute_command("A 2 3")
    runner_result = await runner.run(["2", "3"])

    assert falyx_result == 5
    assert runner_result == 5
    assert falyx_result == runner_result

    assert runner.options_manager is custom_options
    assert runner.command.options_manager is custom_options
    assert runner.options_manager.get("summary", namespace_name="default") is True
    assert runner.options_manager.get_namespace("root") == {}
    assert runner.options_manager.get_namespace("execution") == {}

    assert runner.command is not command
    assert command.options_manager is falyx.options_manager
    assert command.options_manager is not runner.options_manager
