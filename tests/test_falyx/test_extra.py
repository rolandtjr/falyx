from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prompt_toolkit.validation import ValidationError
from rich.table import Table
from rich.text import Text

import falyx.falyx as falyx_module
from falyx import Falyx
from falyx.command import Command
from falyx.exceptions import (
    CommandAlreadyExistsError,
    CommandArgumentError,
    EntryNotFoundError,
    FalyxError,
    InvalidActionError,
    InvalidHookError,
    NotAFalyxError,
    UsageError,
)
from falyx.hook_manager import HookType
from falyx.mode import FalyxMode
from falyx.namespace import FalyxNamespace
from falyx.parser.parser_types import FalyxTLDRExample
from falyx.routing import RouteKind, RouteResult
from falyx.signals import BackSignal, CancelSignal, HelpSignal, QuitSignal


class RecordingConsole:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def print(self, *args, **kwargs) -> None:
        self.calls.append((args, kwargs))

    @property
    def rendered(self) -> str:
        parts: list[str] = []
        for args, _ in self.calls:
            if args:
                value = args[0]
                if isinstance(value, Text):
                    parts.append(value.plain)
                else:
                    parts.append(str(value))
        return "\n".join(parts)


def make_falyx(**overrides) -> Falyx:
    defaults = {
        "program": "fx",
        "description": "Test CLI",
        "enable_help_tips": False,
    }
    defaults.update(overrides)
    return Falyx(**defaults)


def add_deploy(
    flx: Falyx, *, key: str = "D", aliases: list[str] | None = None
) -> Command:
    return flx.add_command(
        key,
        description="Deploy",
        action=lambda: "deployed",
        aliases=aliases if aliases is not None else ["deploy"],
        help_text="Deploy things.",
    )


def route_for(flx: Falyx, kind: RouteKind, **overrides) -> RouteResult:
    values = {
        "kind": kind,
        "namespace": flx,
        "context": flx.get_current_invocation_context(),
    }
    values.update(overrides)
    return RouteResult(**values)


def test_init_with_prompt_history_sanitizes_program_name(tmp_path) -> None:
    flx = Falyx(
        program="my app.cli",
        prompt_history_base_dir=tmp_path,
        enable_prompt_history=True,
    )

    assert flx.history_path == tmp_path / ".my_app_history"
    assert flx.history is not None


def test_str_and_repr_include_identity_fields() -> None:
    flx = Falyx(program="fx", title="Deployments", description="Deploy CLI")

    expected = "Falyx(program='fx', title='Deployments', description='Deploy CLI')"
    assert str(flx) == expected
    assert repr(flx) == expected


def test_add_tldr_examples_delegates_to_root_parser() -> None:
    flx = make_falyx()
    add_deploy(flx)

    flx.add_tldr_examples([("deploy", "--region us-east", "Deploy east")])

    assert flx.parser.tldr_option is not None
    assert flx.parser._tldr_examples[-1].entry_key == "deploy"


def test_rejects_invalid_options_manager() -> None:
    with pytest.raises(NotAFalyxError, match="options_manager"):
        Falyx(options_manager=object())


def test_entry_map_rejects_identifier_collision_with_distinct_entries() -> None:
    flx = make_falyx()
    add_deploy(flx)
    flx.namespaces["N"] = FalyxNamespace(
        key="N",
        description="Nested",
        namespace=make_falyx(),
        aliases=["Deploy"],
    )

    with pytest.raises(CommandAlreadyExistsError, match="identifier 'DEPLOY'"):
        _ = flx._entry_map


def test_get_tip_adds_menu_specific_tips(monkeypatch) -> None:
    flx = make_falyx()
    flx.options_manager.set("mode", FalyxMode.MENU)
    seen: dict[str, list[str]] = {}

    def choose_last(tips: list[str]) -> str:
        seen["tips"] = tips
        return tips[-1]

    monkeypatch.setattr(falyx_module, "choice", choose_last)

    assert flx.get_tip() == "Use '[X]' in menu mode to exit."
    assert "'[Y]' opens the command history viewer." in seen["tips"]


def test_command_key_usage_in_menu_includes_history_and_exit() -> None:
    flx = make_falyx()
    add_deploy(flx)
    flx.options_manager.set("mode", FalyxMode.MENU)

    usage = flx._get_command_keys_usage_string()

    assert "D" in usage
    assert "Y" in usage
    assert "X" in usage


def test_simple_usage_mentions_namespace_when_visible_namespace_exists() -> None:
    flx = make_falyx(simple_usage=True)
    flx.add_submenu("OPS", "Operations", make_falyx())

    fragment = flx._get_usage_fragment(flx.get_current_invocation_context())

    assert "<command or namespace>" in fragment


def test_get_usage_omits_invocation_path_in_menu_mode() -> None:
    flx = make_falyx(usage="custom [args]")
    flx.options_manager.set("mode", FalyxMode.MENU)

    usage = flx._get_usage()

    assert usage == "[bold]usage:[/bold] [white]custom [args][/white]"


@pytest.mark.asyncio
async def test_render_command_tldr_prints_tip_when_examples_render(monkeypatch) -> None:
    flx = make_falyx(enable_help_tips=True)
    flx.console = RecordingConsole()
    monkeypatch.setattr(flx, "get_tip", lambda: "remember aliases")

    command = SimpleNamespace(
        description="Deploy",
        render_tldr=lambda invocation_context: True,
    )

    await flx._render_command_tldr(command)

    assert "remember aliases" in flx.console.rendered


@pytest.mark.asyncio
async def test_render_command_tldr_prints_error_when_no_examples(monkeypatch) -> None:
    flx = make_falyx()
    messages: list[str] = []
    monkeypatch.setattr(
        falyx_module, "print_error", lambda message, **_: messages.append(str(message))
    )
    command = SimpleNamespace(
        description="Deploy",
        render_tldr=lambda invocation_context: False,
    )

    await flx._render_command_tldr(command)

    assert messages == ["No TLDR examples available for 'Deploy'."]


@pytest.mark.asyncio
async def test_render_command_help_delegates_to_tldr(monkeypatch) -> None:
    flx = make_falyx()
    command = SimpleNamespace(description="Deploy")
    context = flx.get_current_invocation_context()
    called: dict[str, object] = {}

    async def fake_tldr(rendered_command, invocation_context=None) -> None:
        called["command"] = rendered_command
        called["context"] = invocation_context

    monkeypatch.setattr(flx, "_render_command_tldr", fake_tldr)

    await flx._render_command_help(command, tldr=True, invocation_context=context)

    assert called == {"command": command, "context": context}


@pytest.mark.asyncio
async def test_render_command_help_prints_tip_when_help_renders(monkeypatch) -> None:
    flx = make_falyx(enable_help_tips=True)
    flx.console = RecordingConsole()
    monkeypatch.setattr(flx, "get_tip", lambda: "read the usage line")
    command = SimpleNamespace(
        description="Deploy",
        render_help=lambda invocation_context: True,
    )

    await flx._render_command_help(command)

    assert "read the usage line" in flx.console.rendered


@pytest.mark.asyncio
async def test_render_command_help_prints_error_when_no_help(monkeypatch) -> None:
    flx = make_falyx()
    messages: list[str] = []
    monkeypatch.setattr(
        falyx_module, "print_error", lambda message, **_: messages.append(str(message))
    )
    command = SimpleNamespace(
        description="Deploy",
        render_help=lambda invocation_context: False,
    )

    await flx._render_command_help(command)

    assert messages == ["No detailed help available for 'Deploy'."]


@pytest.mark.asyncio
async def test_render_tag_help_prints_empty_tag_message() -> None:
    flx = make_falyx()
    flx.console = RecordingConsole()

    await flx._render_tag_help("missing")

    assert "Nothing to show here" in flx.console.rendered


@pytest.mark.asyncio
async def test_render_menu_help_includes_namespaces_and_epilog(monkeypatch) -> None:
    monkeypatch.setattr(
        FalyxNamespace,
        "get_help_signature",
        lambda self, context: (self.key, self.description, ""),
        raising=False,
    )
    flx = make_falyx(epilog="Menu epilog")
    flx.console = RecordingConsole()
    flx.add_submenu("OPS", "Operations namespace", make_falyx())

    await flx._render_menu_help(flx.get_current_invocation_context())

    assert "namespaces" in flx.console.rendered
    assert "Menu epilog" in flx.console.rendered


@pytest.mark.asyncio
async def test_render_cli_help_includes_namespaces_aliases_and_epilog() -> None:
    flx = make_falyx(epilog="CLI epilog")
    flx.console = RecordingConsole()
    flx.add_submenu("OPS", "Operations namespace", make_falyx(), aliases=["operations"])

    await flx._render_cli_help(flx.get_current_invocation_context())

    rendered = flx.console.rendered
    assert "namespaces" in rendered
    assert "OPS | operations" in rendered
    assert "Operations namespace" in rendered
    assert "CLI epilog" in rendered


@pytest.mark.asyncio
async def test_namespace_tldr_prints_empty_message_without_examples() -> None:
    flx = make_falyx(title="Root Menu")
    flx.console = RecordingConsole()

    await flx._render_namespace_tldr_help(flx.get_current_invocation_context())

    assert "No TLDR examples available for 'Root Menu'" in flx.console.rendered


@pytest.mark.asyncio
async def test_namespace_tldr_rejects_stale_unknown_example() -> None:
    flx = make_falyx()
    flx.parser.tldr_option = object()
    flx.parser._tldr_examples.append(
        FalyxTLDRExample(
            entry_key="missing",
            usage="",
            description="Stale example",
        )
    )

    with pytest.raises(EntryNotFoundError) as error:
        await flx._render_namespace_tldr_help(flx.get_current_invocation_context())

    assert error.value.unknown_name == "missing"


def test_help_target_base_context_handles_empty_and_help_command_path() -> None:
    flx = make_falyx()
    base_context = flx.get_current_invocation_context()

    assert flx._help_target_base_context(base_context) is base_context

    help_context = base_context.with_path_segment("H", style=flx.help_command.style)
    stripped = flx._help_target_base_context(help_context)

    assert stripped.typed_path == []


@pytest.mark.asyncio
async def test_render_help_dispatches_to_specific_command(monkeypatch) -> None:
    flx = make_falyx()
    command = add_deploy(flx)
    called: dict[str, object] = {}

    async def fake_command_help(command, tldr=False, invocation_context=None) -> None:
        called["command"] = command
        called["tldr"] = tldr
        called["path"] = list(invocation_context.typed_path)

    monkeypatch.setattr(flx, "_render_command_help", fake_command_help)

    await flx.render_help(key="deploy", tldr=True)

    assert called == {"command": command, "tldr": True, "path": ["deploy"]}


@pytest.mark.asyncio
async def test_render_help_dispatches_to_specific_namespace(monkeypatch) -> None:
    flx = make_falyx()
    submenu = make_falyx()
    called: dict[str, object] = {}
    flx.add_submenu("OPS", "Operations", submenu)

    async def fake_namespace_help(invocation_context=None, tldr=False) -> None:
        called["tldr"] = tldr
        called["path"] = list(invocation_context.typed_path)

    monkeypatch.setattr(submenu, "render_namespace_help", fake_namespace_help)

    await flx.render_help(key="OPS", tldr=True)

    assert called == {"tldr": True, "path": ["OPS"]}


@pytest.mark.asyncio
async def test_render_help_renders_namespace_then_raises_for_unknown_key(
    monkeypatch,
) -> None:
    flx = make_falyx()
    rendered: list[InvocationContext] = []

    async def fake_namespace_help(invocation_context=None, tldr=False) -> None:
        rendered.append(invocation_context)

    monkeypatch.setattr(flx, "render_namespace_help", fake_namespace_help)

    with pytest.raises(EntryNotFoundError) as error:
        await flx.render_help(key="depoy")

    assert rendered
    assert error.value.unknown_name == "depoy"


@pytest.mark.asyncio
async def test_render_help_without_key_tldr_renders_help_command_tldr(
    monkeypatch,
) -> None:
    flx = make_falyx()
    called: dict[str, object] = {}

    async def fake_command_help(command, tldr=False, invocation_context=None) -> None:
        called["command"] = command
        called["tldr"] = tldr

    monkeypatch.setattr(flx, "_render_command_help", fake_command_help)

    await flx.render_help(tldr=True)

    assert called == {"command": flx.help_command, "tldr": True}


@pytest.mark.asyncio
async def test_preview_rejects_namespaces_and_unknown_entries() -> None:
    flx = make_falyx()
    flx.add_submenu("OPS", "Operations", make_falyx())

    with pytest.raises(FalyxError, match="preview mode"):
        await flx._preview("OPS")

    with pytest.raises(EntryNotFoundError) as error:
        await flx._preview("missing")

    assert error.value.unknown_name == "missing"


@pytest.mark.asyncio
async def test_render_version_prints_program_version() -> None:
    flx = make_falyx(program="fx", version="9.9.9")
    flx.console = RecordingConsole()

    await flx._render_version()

    assert "fx v9.9.9" in flx.console.rendered


def test_invalidate_prompt_session_cache_deletes_cached_property_value() -> None:
    flx = make_falyx()
    flx.__dict__["prompt_session"] = object()
    flx._prompt_session = object()

    flx._invalidate_prompt_session_cache()

    assert "prompt_session" not in flx.__dict__
    assert flx._prompt_session is None


def test_bottom_bar_accepts_instance_string_callable_and_rejects_invalid() -> None:
    flx = make_falyx()
    existing_bottom_bar = flx.bottom_bar

    flx.bottom_bar = existing_bottom_bar
    assert flx.bottom_bar is existing_bottom_bar
    assert flx.bottom_bar.key_bindings is flx.key_bindings

    flx.bottom_bar = "static toolbar"
    assert flx._get_bottom_bar_render() == "static toolbar"

    renderer = lambda: "dynamic toolbar"
    flx.bottom_bar = renderer
    assert flx._get_bottom_bar_render() is renderer

    with pytest.raises(FalyxError, match="bottom_bar"):
        flx.bottom_bar = object()


def test_default_bottom_bar_render_is_returned_when_items_exist() -> None:
    flx = make_falyx()
    render = flx._get_bottom_bar_render()

    if flx.bottom_bar.has_items:
        assert render is flx.bottom_bar.render
    else:
        assert render is None


def test_register_all_hooks_rejects_non_callable_hook() -> None:
    flx = make_falyx()

    with pytest.raises(InvalidHookError, match="callable"):
        flx.register_all_hooks(HookType.BEFORE, object())


def test_validate_command_aliases_rejects_duplicate_aliases() -> None:
    flx = make_falyx()

    with pytest.raises(CommandAlreadyExistsError, match="duplicate aliases"):
        flx.add_command(
            "D", description="Deploy", action=lambda: None, aliases=["deploy", "DEPLOY"]
        )


def test_validate_command_aliases_rejects_key_as_alias() -> None:
    flx = make_falyx()

    with pytest.raises(CommandAlreadyExistsError, match="cannot also be an alias"):
        flx.add_command("D", description="Deploy", action=lambda: None, aliases=["D"])


def test_validate_command_aliases_rejects_existing_identifier_collision() -> None:
    flx = make_falyx()

    with pytest.raises(CommandAlreadyExistsError, match="already exist"):
        flx.add_command("H", description="Duplicate Help", action=lambda: None)


def test_update_exit_command_rejects_non_callable_action() -> None:
    flx = make_falyx()

    with pytest.raises(InvalidActionError, match="callable"):
        flx.update_exit_command(key="Q", action="quit")


def test_add_submenu_rejects_non_falyx_submenu() -> None:
    flx = make_falyx()

    with pytest.raises(NotAFalyxError, match="submenu"):
        flx.add_submenu("OPS", "Operations", object())


def test_add_commands_accepts_dicts_and_command_instances() -> None:
    flx = make_falyx()
    reusable = Command(key="B", description="Build", action=lambda: "built")

    commands = flx.add_commands(
        [
            {"key": "D", "description": "Deploy", "action": lambda: "deployed"},
            reusable,
        ]
    )

    assert [command.key for command in commands] == ["D", "B"]
    assert flx.commands["D"].description == "Deploy"
    assert flx.commands["B"].description == "Build"


def test_add_commands_rejects_invalid_items() -> None:
    flx = make_falyx()

    with pytest.raises(FalyxError, match="dictionary or an instance of Command"):
        flx.add_commands([object()])


def test_add_command_from_command_rejects_non_command() -> None:
    flx = make_falyx()

    with pytest.raises(FalyxError, match="instance of Command"):
        flx.add_command_from_command(object())


def test_iter_visible_entries_can_include_builtins() -> None:
    flx = make_falyx()
    visible = flx._iter_visible_entries(include_builtins=True)

    assert any(entry.key == "H" for entry in visible)
    assert any(entry.key == "PVW" for entry in visible)
    assert any(entry.key == "VER" for entry in visible)


def test_build_placeholder_menu_returns_empty_placeholder_without_user_commands() -> None:
    flx = make_falyx()

    assert flx.build_placeholder_menu() == [("", "")]


def test_table_uses_callable_custom_table_and_rejects_invalid_factory() -> None:
    good = make_falyx(custom_table=lambda app: Table(title=app.title))
    assert isinstance(good.table, Table)

    bad = make_falyx(custom_table=lambda app: "not a table")
    with pytest.raises(FalyxError, match="custom_table"):
        _ = bad.table


def test_table_uses_prebuilt_custom_table_instance() -> None:
    table = Table(title="Prebuilt")
    flx = make_falyx(custom_table=table)

    assert flx.table is table


def test_resolve_entry_accepts_unique_prefix_matches() -> None:
    flx = make_falyx()
    command = add_deploy(flx, key="DEPLOY", aliases=[])

    entry, suggestions = flx.resolve_entry("depl")

    assert entry is command
    assert suggestions == []


@pytest.mark.asyncio
async def test_prepare_route_converts_bad_shell_string_to_validation_error() -> None:
    flx = make_falyx()

    with pytest.raises(ValidationError):
        await flx.prepare_route('"unterminated', from_validate=True)


@pytest.mark.asyncio
async def test_prepare_route_converts_bad_shell_string_to_usage_error() -> None:
    flx = make_falyx()

    with pytest.raises(UsageError, match="No closing quotation"):
        await flx.prepare_route('"unterminated')


@pytest.mark.asyncio
async def test_prepare_route_rejects_invalid_raw_argument_type() -> None:
    flx = make_falyx()

    with pytest.raises(AssertionError, match="Validator can only pass"):
        await flx.prepare_route(object(), from_validate=True)

    with pytest.raises(UsageError, match="raw_arguments"):
        await flx.prepare_route(object())


@pytest.mark.asyncio
async def test_prepare_route_preserves_preview_route_without_resolving_command_args() -> (
    None
):
    flx = make_falyx()
    add_deploy(flx)

    route, args, kwargs, execution_args = await flx.prepare_route("?D")

    assert route.is_preview is True
    assert route.kind is RouteKind.COMMAND
    assert args == ()
    assert kwargs == {}
    assert execution_args == {}


@pytest.mark.asyncio
async def test_prepare_route_wraps_route_errors_for_validation(monkeypatch) -> None:
    flx = make_falyx()

    async def fake_resolve_route(*args, **kwargs):
        raise FalyxError("bad route", hint="try deploy")

    monkeypatch.setattr(flx, "resolve_route", fake_resolve_route)

    with pytest.raises(ValidationError) as error:
        await flx.prepare_route("D", from_validate=True)

    assert "try deploy" in str(error.value)


@pytest.mark.asyncio
async def test_prepare_route_wraps_command_argument_errors_for_validation(
    monkeypatch,
) -> None:
    flx = make_falyx()
    command = add_deploy(flx)

    async def fake_resolve_route(*args, **kwargs):
        return route_for(flx, RouteKind.COMMAND, command=command, leaf_argv=["--bad"])

    async def fake_resolve_args(*args, **kwargs):
        raise CommandArgumentError("bad args", hint="use --help")

    monkeypatch.setattr(flx, "resolve_route", fake_resolve_route)
    monkeypatch.setattr(Command, "resolve_args", fake_resolve_args)

    with pytest.raises(ValidationError) as error:
        await flx.prepare_route(["D"], from_validate=True)

    assert "use --help" in str(error.value)


@pytest.mark.asyncio
async def test_render_unknown_route_rejects_preview_namespace_menu() -> None:
    flx = make_falyx()
    route = route_for(flx, RouteKind.NAMESPACE_MENU)

    with pytest.raises(FalyxError, match="preview mode"):
        await flx._render_unknown_route(route)


@pytest.mark.asyncio
async def test_dispatch_route_previews_command_and_unknown_preview(monkeypatch) -> None:
    flx = make_falyx()
    command = SimpleNamespace(key="D", preview=AsyncMock())
    command_route = route_for(
        flx,
        RouteKind.COMMAND,
        command=command,
        is_preview=True,
    )

    await flx._dispatch_route(route=command_route)
    command.preview.assert_awaited_once()

    unknown_route = route_for(
        flx, RouteKind.UNKNOWN, current_head="missing", is_preview=True
    )
    rendered: list[RouteResult] = []

    async def fake_unknown(route):
        rendered.append(route)

    monkeypatch.setattr(flx, "_render_unknown_route", fake_unknown)

    await flx._dispatch_route(route=unknown_route)
    assert rendered == [unknown_route]


@pytest.mark.asyncio
async def test_dispatch_route_unknown_returns_after_rendering(monkeypatch) -> None:
    flx = make_falyx()
    route = route_for(flx, RouteKind.UNKNOWN, current_head="missing")
    rendered: list[RouteResult] = []

    async def fake_unknown(route):
        rendered.append(route)

    monkeypatch.setattr(flx, "_render_unknown_route", fake_unknown)

    assert await flx._dispatch_route(route=route) is None
    assert rendered == [route]


@pytest.mark.asyncio
async def test_dispatch_route_rejects_command_route_without_command() -> None:
    flx = make_falyx()
    route = route_for(flx, RouteKind.COMMAND, command=None)

    with pytest.raises(FalyxError, match="command expected"):
        await flx._dispatch_route(route=route)


@pytest.mark.asyncio
async def test_execute_command_requires_error_policy() -> None:
    flx = make_falyx()

    with pytest.raises(FalyxError, match="requires either"):
        await flx.execute_command("D", raise_on_error=False, wrap_errors=False)


def test_resolve_completion_route_returns_entry_completion_for_unknown_committed_token() -> (
    None
):
    flx = make_falyx()
    context = flx.get_current_invocation_context()

    route = flx.resolve_completion_route(
        ["depoy"],
        stub="",
        cursor_at_end_of_token=False,
        invocation_context=context,
    )

    assert route.expecting_entry is True
    assert route.stub == "depoy"
    assert route.command is None


@pytest.mark.asyncio
async def test_process_command_executes_prompt_input_and_reports_falyx_error(
    monkeypatch,
) -> None:
    flx = make_falyx()
    errors: list[object] = []
    invalidated: list[bool] = []

    class FakeApp:
        def invalidate(self) -> None:
            invalidated.append(True)

    class FakeSession:
        async def prompt_async(self) -> str:
            return "D"

    async def fake_execute_command(*args, **kwargs):
        raise FalyxError("boom")

    monkeypatch.setattr(falyx_module, "get_app", lambda: FakeApp())
    monkeypatch.setattr(falyx_module.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(falyx_module, "patch_stdout", lambda raw=True: nullcontext())
    monkeypatch.setattr(
        falyx_module, "print_error", lambda message, **_: errors.append(message)
    )
    monkeypatch.setattr(flx, "execute_command", fake_execute_command)
    flx.__dict__["prompt_session"] = FakeSession()

    await flx._process_command()

    assert invalidated == [True]
    assert isinstance(errors[0], FalyxError)


@pytest.mark.asyncio
async def test_menu_handles_flow_signals_and_prints_welcome_and_exit(monkeypatch) -> None:
    rendered: list[Falyx] = []
    flx = make_falyx(
        welcome_message="welcome",
        exit_message="goodbye",
        render_menu=lambda app: rendered.append(app),
    )
    flx.console = RecordingConsole()
    signals: list[BaseException] = [
        HelpSignal(),
        BackSignal(),
        CancelSignal(),
        asyncio.CancelledError(),
        QuitSignal(),
    ]

    async def fake_process_command() -> None:
        raise signals.pop(0)

    monkeypatch.setattr(flx, "_process_command", fake_process_command)

    await flx.menu()

    assert rendered == [flx, flx, flx, flx, flx]
    assert "welcome" in flx.console.rendered
    assert "goodbye" in flx.console.rendered


@pytest.mark.asyncio
async def test_run_logs_verbose_unhandled_errors_before_exit(monkeypatch) -> None:
    flx = make_falyx()
    flx.options_manager.set("verbose", True, "root")
    context = flx.get_current_invocation_context()
    route = RouteResult(kind=RouteKind.NAMESPACE_MENU, namespace=flx, context=context)
    logged: list[tuple[tuple, dict]] = []

    async def fake_prepare_route(*args, **kwargs):
        return route, (), {}, {}

    async def fake_dispatch_route(*args, **kwargs):
        raise FalyxError("boom")

    monkeypatch.setattr(flx, "prepare_route", fake_prepare_route)
    monkeypatch.setattr(flx, "_dispatch_route", fake_dispatch_route)
    monkeypatch.setattr(falyx_module.sys, "argv", ["fx", "D"])
    monkeypatch.setattr(falyx_module, "print_error", lambda message, **_: None)
    monkeypatch.setattr(
        falyx_module.logger,
        "error",
        lambda *args, **kwargs: logged.append((args, kwargs)),
    )

    with pytest.raises(SystemExit) as error:
        await flx.run()

    assert error.value.code == 1
    assert logged
    assert logged[0][1]["exc_info"] is True
