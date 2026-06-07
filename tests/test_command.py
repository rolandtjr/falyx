# test_command.py
import logging
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

import falyx.command as command_module
from falyx.action import Action, BaseAction, BaseIOAction, ChainedAction
from falyx.command import Command
from falyx.exceptions import CommandArgumentError, InvalidHookError, NotAFalyxError
from falyx.execution_option import ExecutionOption
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.parser.command_argument_parser import CommandArgumentParser
from falyx.retry import RetryPolicy
from falyx.signals import CancelSignal

asyncio_default_fixture_loop_scope = "function"


class CaptureConsole:
    def __init__(self) -> None:
        self.printed: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.printed.append((args, kwargs))


class FakeBaseAction(BaseAction):
    def __init__(
        self,
        name: str = "FakeAction",
        *,
        result: Any = "ok",
        infer_target: Callable[..., Any] | None = None,
        metadata: dict[str, Any] | None = None,
        never_prompt: bool | None = None,
    ) -> None:
        super().__init__(name, never_prompt=never_prompt)
        self.result = result
        self.infer_target = infer_target or (lambda: None)
        self.metadata = metadata
        self.preview_calls = 0
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def _run(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return self.result

    async def preview(self, parent=None):
        self.preview_calls += 1
        if parent is not None:
            parent.add("fake preview")
        return None

    def get_infer_target(self):
        return self.infer_target, self.metadata

    def clone(self) -> "FakeBaseAction":
        return FakeBaseAction(
            self.name,
            result=self.result,
            infer_target=self.infer_target,
            metadata=self.metadata,
            never_prompt=self.local_never_prompt,
        )


def make_command(**overrides: Any) -> Command:
    defaults = dict(
        key="D",
        description="Deploy command",
        action=lambda *args, **kwargs: {"args": args, "kwargs": kwargs},
        auto_args=False,
    )
    defaults.update(overrides)
    return Command.build(**defaults)


def formatted_plain_text(formatted_text) -> str:
    return "".join(fragment for _, fragment in list(formatted_text))


@pytest.fixture(autouse=True)
def clean_registry():
    er.clear()
    yield
    er.clear()


async def dummy_action():
    return "ok"


class DummyInputAction(BaseIOAction):
    async def _run(self, *args, **kwargs):
        return "needs input"

    async def preview(self, parent=None):
        pass


@pytest.mark.asyncio
async def test_command_creation():
    """Test if Command can be created with a callable."""
    action = Action("test_action", dummy_action)
    cmd = Command(key="TEST", description="Test Command", action=action)
    assert cmd.key == "TEST"
    assert cmd.description == "Test Command"
    assert cmd.action == action

    result = await cmd()
    assert result == "ok"
    assert cmd.result == "ok"


def test_command_str():
    """Test if Command string representation is correct."""
    action = Action("test_action", dummy_action)
    cmd = Command(key="TEST", description="Test Command", action=action)
    print(cmd)
    assert (
        str(cmd)
        == "Command(key='TEST', description='Test Command' action='Action(name='test_action', action=dummy_action, args=(), kwargs={}, retry=False, rollback=False)')"
    )


def test_enable_retry():
    """Command should enable retry if action is an Action and  retry is set to True."""
    cmd = Command(
        key="A",
        description="Retry action",
        action=Action(
            name="retry_action",
            action=lambda: 42,
        ),
        retry=True,
    )
    assert cmd.retry is True
    assert cmd.action.retry_policy.enabled is True


def test_enable_retry_with_retry_policy():
    """Command should enable retry if action is an Action and retry_policy is set."""
    retry_policy = RetryPolicy(
        max_retries=3,
        delay=1,
        backoff=2,
        enabled=True,
    )
    cmd = Command(
        key="B",
        description="Retry action with policy",
        action=Action(
            name="retry_action_with_policy",
            action=lambda: 42,
        ),
        retry_policy=retry_policy,
    )
    assert cmd.action.retry_policy.enabled is True
    assert cmd.action.retry_policy == retry_policy


def test_enable_retry_not_action():
    """Command should not enable retry if action is not an Action."""
    cmd = Command(
        key="C",
        description="Retry action",
        action=DummyInputAction(
            name="dummy_input_action",
        ),
        retry=True,
    )
    assert cmd.retry is True
    with pytest.raises(Exception) as exc_info:
        assert cmd.action.retry_policy.enabled is False
    assert "'DummyInputAction' object has no attribute 'retry_policy'" in str(
        exc_info.value
    )


def test_chain_retry_all():
    """retry_all should retry all Actions inside a ChainedAction recursively."""
    chain = ChainedAction(
        name="ChainWithRetry",
        actions=[
            Action(name="action1", action=lambda: 1),
            Action(name="action2", action=lambda: 2),
        ],
    )
    cmd = Command(
        key="D",
        description="Chain with retry",
        action=chain,
        retry_all=True,
    )

    assert cmd.retry_all is True
    assert cmd.retry_policy.enabled is True
    assert chain.actions[0].retry_policy.enabled is True
    assert chain.actions[1].retry_policy.enabled is True


def test_chain_retry_all_not_base_action():
    """retry_all should not be set if action is not a ChainedAction."""
    cmd = Command(
        key="E",
        description="Chain with retry",
        action=DummyInputAction(
            name="dummy_input_action",
        ),
        retry_all=True,
    )
    assert cmd.retry_all is True
    with pytest.raises(Exception) as exc_info:
        assert cmd.action.retry_policy.enabled is False
    assert "'DummyInputAction' object has no attribute 'retry_policy'" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_command_exception_handling():
    """Test if Command handles exceptions correctly."""

    async def bad_action():
        raise ZeroDivisionError("This is a test exception")

    cmd = Command(key="TEST", description="Test Command", action=bad_action)

    with pytest.raises(ZeroDivisionError):
        await cmd()

    assert cmd.result is None
    assert isinstance(cmd._context.exception, ZeroDivisionError)


def test_command_bad_action():
    """Test if Command raises an exception when action is not callable."""
    with pytest.raises(TypeError) as exc_info:
        Command(key="TEST", description="Test Command", action="not_callable")
    assert str(exc_info.value) == "Action must be a callable or an instance of BaseAction"


def test_command_bad_options_manager():
    """Test if Command raises an exception when options_manager is not a dict or callable."""
    with pytest.raises(ValidationError) as exc_info:
        Command(
            key="TEST",
            description="Test Command",
            action=dummy_action,
            options_manager="not_a_dict_or_callable",
        )
    assert "Input should be an instance of OptionsManager" in str(exc_info.value)


@pytest.mark.asyncio
async def test_resolve_args_uses_custom_parser_and_splits_string_input() -> None:
    seen: list[list[str]] = []

    def custom_parser(tokens: list[str]):
        seen.append(tokens)
        return (("parsed",), {"tokens": tokens}, {"summary": True})

    command = make_command(custom_parser=custom_parser)

    args, kwargs, execution_args = await command.resolve_args("--name 'Ada Lovelace'")

    assert seen == [["--name", "Ada Lovelace"]]
    assert args == ("parsed",)
    assert kwargs == {"tokens": ["--name", "Ada Lovelace"]}
    assert execution_args == {"summary": True}


@pytest.mark.asyncio
async def test_resolve_args_rejects_non_callable_custom_parser() -> None:
    command = make_command(custom_parser=lambda tokens: ((), {}, {}))
    command.custom_parser = object()

    with pytest.raises(NotAFalyxError, match="custom_parser must be a callable"):
        await command.resolve_args([])


@pytest.mark.asyncio
async def test_resolve_args_wraps_bad_shell_input_for_custom_parser() -> None:
    command = make_command(custom_parser=lambda tokens: ((), {}, {}))

    with pytest.raises(CommandArgumentError, match="Failed to parse arguments"):
        await command.resolve_args("'unterminated")


@pytest.mark.asyncio
async def test_resolve_args_wraps_bad_shell_input_for_command_argument_parser() -> None:
    command = make_command()

    with pytest.raises(CommandArgumentError, match="Failed to parse arguments"):
        await command.resolve_args("'unterminated")


@pytest.mark.asyncio
async def test_resolve_args_rejects_missing_parser_when_no_custom_parser_exists() -> None:
    command = make_command(custom_parser=lambda tokens: ((), {}, {}))
    command.custom_parser = None
    command.arg_parser = None

    with pytest.raises(NotAFalyxError, match="Command has no parser configured"):
        await command.resolve_args([])


@pytest.mark.asyncio
async def test_resolve_args_rejects_invalid_arg_parser_instance() -> None:
    command = make_command()
    command.arg_parser = object()

    with pytest.raises(NotAFalyxError, match="arg_parser must be an instance"):
        await command.resolve_args([])


@pytest.mark.asyncio
async def test_explicit_argument_definitions_are_added_to_default_parser() -> None:
    command = make_command(
        arguments=[
            {
                "flags": ("target",),
                "help": "Deployment target",
            },
            {
                "flags": ("--region",),
                "default": "us-east",
            },
        ]
    )

    args, kwargs, execution_args = await command.resolve_args(
        ["api", "--region", "us-west"]
    )

    assert args == ("api",)
    assert kwargs == {"region": "us-west"}
    assert execution_args == {}


@pytest.mark.asyncio
async def test_argument_config_callback_configures_existing_parser() -> None:
    def configure(parser: CommandArgumentParser) -> None:
        parser.add_argument("--region", default="us-east")

    command = make_command(argument_config=configure)

    args, kwargs, execution_args = await command.resolve_args(["--region", "us-west"])

    assert args == ()
    assert kwargs == {"region": "us-west"}
    assert execution_args == {}


def test_base_action_inference_merges_action_metadata() -> None:
    def deploy(region: str) -> None:
        return None

    action = FakeBaseAction(
        infer_target=deploy,
        metadata={"region": {"help": "Region from action metadata"}},
    )

    command = Command.build(
        key="D",
        description="Deploy command",
        action=action,
        auto_args=True,
    )

    assert command.arg_metadata["region"] == {"help": "Region from action metadata"}
    assert isinstance(command.arg_parser, CommandArgumentParser)
    assert "region" in command.arg_parser._positional


def test_build_validates_parser_runtime_dependencies_and_retry_policy() -> None:
    with pytest.raises(NotAFalyxError, match="arg_parser"):
        make_command(arg_parser=object())

    with pytest.raises(NotAFalyxError, match="options_manager"):
        make_command(options_manager=object())

    with pytest.raises(InvalidHookError, match="HookManager"):
        make_command(hooks=object())

    with pytest.raises(NotAFalyxError, match="retry_policy"):
        make_command(retry_policy=object())


def test_build_normalizes_execution_options_and_registers_hook_lists() -> None:
    async def before(_context) -> None:
        return None

    async def success(_context) -> None:
        return None

    async def error(_context) -> None:
        return None

    async def after(_context) -> None:
        return None

    async def teardown(_context) -> None:
        return None

    command = make_command(
        execution_options=["summary", ExecutionOption.CONFIRM],
        before_hooks=[before],
        success_hooks=[success],
        error_hooks=[error],
        after_hooks=[after],
        teardown_hooks=[teardown],
        spinner=True,
    )

    assert ExecutionOption.SUMMARY in command.execution_options
    assert ExecutionOption.CONFIRM in command.execution_options
    assert before in command.hooks._hooks[HookType.BEFORE]
    assert success in command.hooks._hooks[HookType.ON_SUCCESS]
    assert error in command.hooks._hooks[HookType.ON_ERROR]
    assert after in command.hooks._hooks[HookType.AFTER]
    assert teardown in command.hooks._hooks[HookType.ON_TEARDOWN]
    assert command.hooks._hooks[HookType.BEFORE]
    assert command.hooks._hooks[HookType.ON_TEARDOWN]


def test_model_post_init_warns_for_retry_flags_on_plain_callable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        make_command(retry=True, retry_all=True)

    assert "Retry requested" in caplog.text
    assert "Retry all requested" in caplog.text


def test_retry_all_for_base_action_enables_policy_recursively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    action = FakeBaseAction()
    calls: list[tuple[BaseAction, RetryPolicy]] = []

    def fake_enable_retries_recursively(
        base_action: BaseAction, policy: RetryPolicy
    ) -> None:
        calls.append((base_action, policy))

    monkeypatch.setattr(
        command_module,
        "enable_retries_recursively",
        fake_enable_retries_recursively,
    )

    command = Command.build(
        key="D",
        description="Deploy command",
        action=action,
        retry_all=True,
        auto_args=False,
    )

    assert command.retry_policy.enabled is True
    assert calls == [(action, command.retry_policy)]


def test_logging_hooks_are_registered_on_base_action() -> None:
    action = FakeBaseAction()

    Command.build(
        key="D",
        description="Deploy command",
        action=action,
        logging_hooks=True,
        auto_args=False,
    )

    assert any(action.hooks._hooks.values())


def test_ignore_in_history_is_copied_to_base_action() -> None:
    action = FakeBaseAction()

    Command.build(
        key="D",
        description="Deploy command",
        action=action,
        ignore_in_history=True,
        auto_args=False,
    )

    assert action.ignore_in_history is True


def test_retry_flag_enables_retry_on_action_instance() -> None:
    action = Action("DeployAction", lambda: "ok")

    Command.build(
        key="D",
        description="Deploy command",
        action=action,
        retry=True,
        auto_args=False,
    )

    assert action.retry_policy.enabled is True


def test_confirmation_prompt_uses_custom_message() -> None:
    command = make_command(confirm_message="Ship it?")

    assert list(command._confirmation_prompt) == [("class:confirm", "Ship it?")]


def test_confirmation_prompt_describes_default_callable_with_static_inputs() -> None:
    def deploy() -> str:
        return "ok"

    command = Command.build(
        key="D",
        description="Deploy command",
        action=deploy,
        args=("api",),
        kwargs={"region": "us-east"},
        auto_args=False,
    )

    plain_text = formatted_plain_text(command._confirmation_prompt)

    assert "Confirm execution of" in plain_text
    assert "D" in plain_text
    assert "Deploy command" in plain_text
    assert "calls" in plain_text
    assert "args=('api',)" in plain_text
    assert "kwargs={'region': 'us-east'}" in plain_text


def test_confirmation_prompt_uses_base_action_name() -> None:
    command = Command.build(
        key="D",
        description="Deploy command",
        action=FakeBaseAction("DeployAction"),
        auto_args=False,
    )

    assert "DeployAction" in formatted_plain_text(command._confirmation_prompt)


@pytest.mark.asyncio
async def test_confirmation_cancel_previews_then_raises_cancel_signal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = make_command(confirm=True, preview_before_confirm=True)
    previewed: list[str] = []
    confirmed_prompts: list[Any] = []

    async def fake_preview(self: Command) -> None:
        previewed.append(self.key)

    async def fake_confirm(prompt) -> bool:
        confirmed_prompts.append(prompt)
        return False

    monkeypatch.setattr(Command, "preview", fake_preview)
    monkeypatch.setattr(command_module, "confirm_async", fake_confirm)

    with pytest.raises(CancelSignal, match="Cancelled by confirmation"):
        await command()

    assert previewed == ["D"]
    assert confirmed_prompts


@pytest.mark.asyncio
async def test_confirmation_accepts_and_executes_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_confirm(_prompt) -> bool:
        return True

    def action() -> str:
        calls.append("ran")
        return "done"

    monkeypatch.setattr(command_module, "confirm_async", fake_confirm)
    command = Command.build(
        key="D",
        description="Deploy command",
        action=action,
        confirm=True,
        preview_before_confirm=False,
        auto_args=False,
    )

    assert await command() == "done"
    assert calls == ["ran"]


def test_get_option_returns_default_when_no_options_manager_is_available() -> None:
    command = make_command()
    command.options_manager = None

    assert command.get_option("missing", "fallback") == "fallback"


def test_primary_alias_falls_back_to_command_key() -> None:
    assert make_command(aliases=[]).primary_alias == "D"


def test_usage_reports_no_arguments_when_parser_is_absent() -> None:
    command = make_command(custom_parser=lambda tokens: ((), {}, {}))

    assert command.usage == "No arguments defined."


def test_usage_delegates_to_arg_parser_when_available() -> None:
    command = make_command(aliases=["deploy"])

    assert "D" in command.usage
    assert "deploy" in command.usage


def test_help_signature_full_mode_includes_help_text_and_tags() -> None:
    command = make_command(help_text="Detailed deploy help", tags=["deploy", "cloud"])

    usage, description, tags = command.help_signature

    assert "D" in usage
    assert "Detailed deploy help" in description
    assert "deploy, cloud" in tags


def test_help_signature_simple_mode_uses_key_and_aliases() -> None:
    command = make_command(
        aliases=["deploy"],
        help_text="Detailed deploy help",
        simple_help_signature=True,
    )

    usage, description, tags = command.help_signature

    assert "D" in usage
    assert "deploy" in usage
    assert "Detailed deploy help" in description
    assert tags == ""


def test_log_summary_delegates_to_existing_context() -> None:
    command = make_command()
    calls: list[str] = []
    command._context = SimpleNamespace(log_summary=lambda: calls.append("logged"))

    command.log_summary()

    assert calls == ["logged"]


def test_render_usage_prefers_custom_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = CaptureConsole()
    monkeypatch.setattr(command_module, "console", captured)
    command = make_command(custom_usage=lambda: "custom usage")

    command.render_usage()

    assert captured.printed[0][0] == ("custom usage",)


def test_render_usage_falls_back_to_command_key_without_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = CaptureConsole()
    monkeypatch.setattr(command_module, "console", captured)
    command = make_command(custom_parser=lambda tokens: ((), {}, {}))

    command.render_usage()

    assert captured.printed[0][0] == ("[bold]usage:[/] D",)


def test_render_help_and_tldr_custom_renderers_return_true(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = CaptureConsole()
    monkeypatch.setattr(command_module, "console", captured)
    command = make_command(
        custom_help=lambda: "custom help",
        custom_tldr=lambda: "custom tldr",
    )

    assert command.render_help() is True
    assert command.render_tldr() is True
    assert [printed[0][0] for printed in captured.printed] == [
        "custom help",
        "custom tldr",
    ]


def test_render_help_and_tldr_return_false_without_parser_or_custom_renderer() -> None:
    command = make_command(custom_parser=lambda tokens: ((), {}, {}))

    assert command.render_help() is False
    assert command.render_tldr() is False


@pytest.mark.asyncio
async def test_preview_renders_plain_callable_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = CaptureConsole()
    monkeypatch.setattr(command_module, "console", captured)

    def deploy() -> str:
        return "ok"

    command = Command.build(
        key="D",
        description="Deploy command",
        action=deploy,
        args=("api",),
        kwargs={"region": "us-east"},
        help_text="Preview help",
        auto_args=False,
    )

    await command.preview()

    rendered = "\n".join(str(args[0]) for args, _ in captured.printed)
    assert "Command:" in rendered
    assert "Preview help" in rendered
    assert "Would call:" in rendered
    assert "args=('api',), kwargs={'region': 'us-east'}" in rendered


@pytest.mark.asyncio
async def test_preview_renders_base_action_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = CaptureConsole()
    monkeypatch.setattr(command_module, "console", captured)
    action = FakeBaseAction("DeployAction")
    command = Command.build(
        key="D",
        description="Deploy command",
        action=action,
        help_text="Preview help",
        auto_args=False,
    )

    await command.preview()

    assert action.preview_calls == 1
    assert captured.printed


@pytest.mark.asyncio
async def test_call_merges_static_and_invocation_inputs_and_triggers_hooks() -> None:
    events: list[tuple[str, Any]] = []

    async def before(context) -> None:
        events.append(("before", context.args))

    async def success(context) -> None:
        events.append(("success", context.result))

    async def after(context) -> None:
        events.append(("after", context.result))

    async def teardown(context) -> None:
        events.append(("teardown", context.result))

    def action(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"args": args, "kwargs": kwargs}

    command = Command.build(
        key="D",
        description="Deploy command",
        action=action,
        args=("static",),
        kwargs={"region": "us-east"},
        before_hooks=[before],
        success_hooks=[success],
        after_hooks=[after],
        teardown_hooks=[teardown],
        auto_args=False,
    )

    result = await command("runtime", region="us-west")

    assert result == {
        "args": ("runtime", "static"),
        "kwargs": {"region": "us-west"},
    }
    assert command.result == result
    assert events == [
        ("before", ("runtime", "static")),
        ("success", result),
        ("after", result),
        ("teardown", result),
    ]


@pytest.mark.asyncio
async def test_call_triggers_error_after_and_teardown_hooks_on_failure() -> None:
    events: list[tuple[str, str | None]] = []

    async def on_error(context) -> None:
        events.append(("error", str(context.exception)))

    async def after(context) -> None:
        events.append(("after", str(context.exception)))

    async def teardown(context) -> None:
        events.append(("teardown", str(context.exception)))

    def action() -> None:
        raise RuntimeError("boom")

    command = Command.build(
        key="D",
        description="Deploy command",
        action=action,
        error_hooks=[on_error],
        after_hooks=[after],
        teardown_hooks=[teardown],
        auto_args=False,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await command()

    assert events == [
        ("error", "boom"),
        ("after", "boom"),
        ("teardown", "boom"),
    ]


def test_str_includes_command_identity() -> None:
    text = str(make_command())

    assert "Command(key='D'" in text
    assert "Deploy command" in text


def test_clone_with_overrides_clones_parser_hooks_and_base_action() -> None:
    action = FakeBaseAction("DeployAction")

    async def before(_context) -> None:
        return None

    command = Command.build(
        key="D",
        description="Deploy command",
        action=action,
        aliases=["deploy"],
        before_hooks=[before],
        auto_args=False,
    )

    clone = command.clone_with_overrides(
        key="P",
        description="Promote command",
        aliases=["promote"],
    )

    assert clone.key == "P"
    assert clone.description == "Promote command"
    assert clone.aliases == ["promote"]
    assert clone.action is not command.action
    assert isinstance(clone.action, FakeBaseAction)
    assert clone.hooks is not command.hooks
    assert before in clone.hooks._hooks[HookType.BEFORE]
    assert isinstance(clone.arg_parser, CommandArgumentParser)
    assert clone.arg_parser.command_key == "P"


def test_clone_with_overrides_can_replace_action_and_execution_options() -> None:
    command = make_command(execution_options=["summary"])

    def replacement() -> str:
        return "replacement"

    clone = command.clone_with_overrides(
        action=replacement,
        execution_options=[ExecutionOption.CONFIRM],
        simple_help_signature=True,
    )

    assert clone.action is not command.action
    assert ExecutionOption.CONFIRM in clone.execution_options
    assert ExecutionOption.SUMMARY not in clone.execution_options
    assert clone.simple_help_signature is True
