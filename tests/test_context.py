from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from rich.console import Console

from falyx.context import ExecutionContext, InvocationContext, SharedContext
from falyx.mode import FalyxMode


class DummyAction:
    def __init__(self, name: str = "DummyAction") -> None:
        self.name = name

    def __str__(self) -> str:
        return self.name


def make_execution_context(**overrides: Any) -> ExecutionContext:
    defaults: dict[str, Any] = {
        "name": "Build",
        "action": DummyAction("build"),
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


def make_shared_context(**overrides: Any) -> SharedContext:
    defaults: dict[str, Any] = {
        "name": "Workflow",
        "action": DummyAction("workflow"),
    }
    defaults.update(overrides)
    return SharedContext(**defaults)


def test_execution_context_get_shared_context_returns_existing_context() -> None:
    shared = make_shared_context()
    context = make_execution_context(shared_context=shared)

    assert context.get_shared_context() is shared


def test_execution_context_get_shared_context_raises_when_missing() -> None:
    context = make_execution_context()

    with pytest.raises(ValueError, match="SharedContext is not set"):
        context.get_shared_context()


def test_execution_context_duration_handles_not_started_running_and_stopped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = make_execution_context()
    assert context.duration is None

    context.start_time = 10.0
    context.end_time = None
    monkeypatch.setattr("falyx.context.time.perf_counter", lambda: 12.5)
    assert context.duration == pytest.approx(2.5)

    context.end_time = 14.0
    assert context.duration == pytest.approx(4.0)


def test_execution_context_start_and_stop_timer_populate_timer_fields() -> None:
    context = make_execution_context()

    context.start_timer()
    assert context.start_wall is not None
    assert context.start_time is not None

    context.stop_timer()
    assert context.end_wall is not None
    assert context.end_time is not None
    assert context.duration is not None
    assert context.duration >= 0


def test_execution_context_exception_setter_records_traceback_and_status() -> None:
    context = make_execution_context(result="ignored after failure")

    context.exception = RuntimeError("boom")

    assert isinstance(context.exception, RuntimeError)
    assert context.success is False
    assert context.status == "ERROR"
    assert context.traceback is not None
    assert "RuntimeError: boom" in context.traceback


def test_execution_context_as_dict_includes_result_exception_traceback_duration_and_extra() -> (
    None
):
    context = make_execution_context(
        result={"artifact": "dist/app.whl"},
        start_time=2.0,
        end_time=5.25,
        extra={"attempt": 2},
    )
    context.exception = ValueError("invalid build")

    summary = context.as_dict()

    assert summary["name"] == "Build"
    assert summary["result"] == {"artifact": "dist/app.whl"}
    assert summary["exception"] == "ValueError('invalid build')"
    assert "ValueError: invalid build" in summary["traceback"]
    assert summary["duration"] == pytest.approx(3.25)
    assert summary["extra"] == {"attempt": 2}


def test_execution_context_signature_formats_args_and_kwargs() -> None:
    context = make_execution_context(args=("src", 3), kwargs={"verbose": True})

    assert context.signature == "build ('src', 3, verbose=True)"


def test_execution_context_log_summary_prints_success_to_context_console() -> None:
    recording_console = Console(record=True, width=160)
    context = make_execution_context(
        result="ok",
        start_time=1.0,
        end_time=2.5,
        start_wall=datetime(2026, 6, 7, 11, 0, 0),
        end_wall=datetime(2026, 6, 7, 11, 0, 2),
        console=recording_console,
    )

    context.log_summary()

    output = recording_console.export_text()
    assert "[SUMMARY] Build" in output
    assert "Start: 11:00:00" in output
    assert "End: 11:00:02" in output
    assert "Duration: 1.500s" in output
    assert "Result: ok" in output


def test_execution_context_log_summary_uses_logger_and_includes_exception() -> None:
    messages: list[str] = []
    context = make_execution_context(
        result="unused",
        start_time=10.0,
        end_time=11.0,
    )
    context.exception = OSError("disk full")

    context.log_summary(logger=messages.append)

    assert len(messages) == 1
    assert "[SUMMARY] Build" in messages[0]
    assert "Duration: 1.000s" in messages[0]
    assert "Exception: OSError('disk full')" in messages[0]


def test_execution_context_to_log_line_renders_success_and_error_states() -> None:
    success = make_execution_context(result="ok", start_time=1.0, end_time=1.5)
    failure = make_execution_context(result=None, start_time=2.0, end_time=3.0)
    failure.exception = LookupError("missing")

    assert success.to_log_line() == (
        "[Build] status=OK duration=0.500s result='ok' exception=None"
    )
    assert failure.to_log_line() == (
        "[Build] status=ERROR duration=1.000s result=None "
        "exception=LookupError: missing"
    )


def test_execution_context_str_and_repr_render_success_with_no_duration() -> None:
    context = make_execution_context(result=["ok"])

    text = str(context)
    debug = repr(context)

    assert "<ExecutionContext 'Build' | OK | Duration: n/a" in text
    assert "Result: ['ok']" in text
    assert "ExecutionContext(name='Build', duration=n/a" in debug
    assert "result=['ok']" in debug


def test_execution_context_str_and_repr_render_exception_with_duration() -> None:
    context = make_execution_context(start_time=1.0, end_time=1.75)
    context.exception = RuntimeError("failed")

    text = str(context)
    debug = repr(context)

    assert "<ExecutionContext 'Build' | ERROR | Duration: 0.750s" in text
    assert "Exception: failed" in text
    assert "duration=0.750" in debug
    assert "exception=RuntimeError('failed')" in debug


def test_shared_context_records_results_errors_and_share_values() -> None:
    shared = make_shared_context()
    error = RuntimeError("step failed")

    shared.add_result("first")
    shared.add_error(1, error)
    shared.set("artifact", "dist/app.whl")

    assert shared.results == ["first"]
    assert shared.errors == [(1, error)]
    assert shared.get("artifact") == "dist/app.whl"
    assert shared.get("missing", "default") == "default"
    assert shared.last_result() == "first"


def test_shared_context_last_result_returns_none_when_sequential_context_has_no_results() -> (
    None
):
    shared = make_shared_context()

    assert shared.last_result() is None


def test_shared_context_set_shared_result_does_not_append_for_sequential_context() -> (
    None
):
    shared = make_shared_context(is_concurrent=False)

    shared.set_shared_result("shared-value")

    assert shared.shared_result == "shared-value"
    assert shared.results == []
    assert shared.last_result() is None


def test_shared_context_set_shared_result_appends_and_reads_from_concurrent_context() -> (
    None
):
    shared = make_shared_context(is_concurrent=True)

    shared.set_shared_result("group-value")

    assert shared.shared_result == "group-value"
    assert shared.results == ["group-value"]
    assert shared.last_result() == "group-value"


def test_shared_context_str_marks_sequential_and_concurrent_modes() -> None:
    sequential = make_shared_context(results=["a"])
    concurrent = make_shared_context(is_concurrent=True, results=["b"])

    assert "<SequentialSharedContext 'Workflow'" in str(sequential)
    assert "Results: ['a']" in str(sequential)
    assert "<ConcurrentSharedContext 'Workflow'" in str(concurrent)
    assert "Results: ['b']" in str(concurrent)


def test_invocation_context_menu_path_segment_operations_are_immutable() -> None:
    root = InvocationContext(program="falyx", mode=FalyxMode.MENU)
    one = root.with_path_segment("admin", style="cyan")
    two = one.with_path_segment("deploy", style="green")
    trimmed = two.without_last_path_segment()

    assert root.typed_path == []
    assert root.segments == []
    assert one.typed_path == ["admin"]
    assert one.segments[0].text == "admin"
    assert str(one.segments[0].style) == "cyan"
    assert two.typed_path == ["admin", "deploy"]
    assert trimmed.typed_path == ["admin"]
    assert trimmed.segments[0].text == "admin"
    assert root.without_last_path_segment() is root


def test_invocation_context_plain_path_omits_program_in_menu_mode() -> None:
    context = (
        InvocationContext(program="falyx", mode=FalyxMode.MENU)
        .with_path_segment("admin")
        .with_path_segment("deploy")
    )

    assert context.is_cli_mode is False
    assert context.plain_path == "admin deploy"


def test_invocation_context_plain_path_includes_program_in_cli_mode() -> None:
    context = (
        InvocationContext(program="falyx", mode=FalyxMode.COMMAND)
        .with_path_segment("admin")
        .with_path_segment("deploy")
    )

    assert context.is_cli_mode is True
    assert context.plain_path == "falyx admin deploy"


def test_invocation_context_plain_path_handles_cli_context_without_program() -> None:
    context = InvocationContext(mode=FalyxMode.COMMAND).with_path_segment("deploy")

    assert context.plain_path == "deploy"


def test_invocation_context_markup_path_styles_program_and_segments_and_escapes_text() -> (
    None
):
    context = (
        InvocationContext(
            program="falyx[dev]",
            program_style="bold blue",
            mode=FalyxMode.COMMAND,
        )
        .with_path_segment("admin[ops]", style="cyan")
        .with_path_segment("deploy", style="green")
    )

    assert context.markup_path == (
        "[bold blue]falyx\\[dev][/bold blue] "
        "[cyan]admin\\[ops][/cyan] "
        "[green]deploy[/green]"
    )


def test_invocation_context_markup_path_handles_unstyled_program_and_segments() -> None:
    context = (
        InvocationContext(program="falyx", mode=FalyxMode.COMMAND)
        .with_path_segment("admin[ops]")
        .with_path_segment("deploy")
    )

    assert context.markup_path == "falyx admin\\[ops] deploy"


def test_invocation_context_markup_path_omits_program_in_menu_mode() -> None:
    context = (
        InvocationContext(
            program="falyx",
            program_style="bold blue",
            mode=FalyxMode.MENU,
        )
        .with_path_segment("admin", style="cyan")
        .with_path_segment("deploy")
    )

    assert context.markup_path == "[cyan]admin[/cyan] deploy"
