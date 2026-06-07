from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

import pytest
from rich.console import Console
from rich.table import Table

from falyx.execution_registry import ExecutionRegistry


@dataclass
class DummyAction:
    ignore_in_history: bool = False


class DummyContext:
    def __init__(
        self,
        name: str,
        *,
        result: Any = None,
        exception: Exception | None = None,
        traceback: str = "",
        signature: str | None = None,
        start_time: float | None = 1_700_000_000.0,
        end_time: float | None = 1_700_000_001.0,
        duration: float | None = 1.25,
        ignore_in_history: bool = False,
    ) -> None:
        self.index = -1
        self.name = name
        self.result = result
        self.exception = exception
        self.traceback = traceback
        self.signature = signature or f"{name}()"
        self.start_time = start_time
        self.end_time = end_time
        self.duration = duration
        self.action = DummyAction(ignore_in_history=ignore_in_history)
        self.success = exception is None

    def to_log_line(self) -> str:
        return f"log:{self.name}:{self.index}"


class CaptureConsole:
    def __init__(self) -> None:
        self.printed: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.printed.append((args, kwargs))

    def rendered_text(self) -> str:
        output = Console(record=True, width=160)
        for args, kwargs in self.printed:
            output.print(*args, **kwargs)
        return output.export_text()


@pytest.fixture(autouse=True)
def isolated_registry() -> Iterator[CaptureConsole]:
    original_console = ExecutionRegistry._console
    capture = CaptureConsole()

    ExecutionRegistry._console = capture  # type: ignore[assignment]
    ExecutionRegistry._store_by_name.clear()
    ExecutionRegistry._store_by_index.clear()
    ExecutionRegistry._store_all.clear()
    ExecutionRegistry._index = 0

    yield capture

    ExecutionRegistry._store_by_name.clear()
    ExecutionRegistry._store_by_index.clear()
    ExecutionRegistry._store_all.clear()
    ExecutionRegistry._index = 0
    ExecutionRegistry._console = original_console


def record_context(*args: Any, **kwargs: Any) -> DummyContext:
    context = DummyContext(*args, **kwargs)
    ExecutionRegistry.record(context)  # type: ignore[arg-type]
    return context


def latest_printed_table(console: CaptureConsole) -> Table:
    assert console.printed
    table = console.printed[-1][0][0]
    assert isinstance(table, Table)
    return table


def test_record_assigns_indexes_and_populates_all_lookup_stores() -> None:
    first = record_context("Build", result="ok")
    second = record_context("Build", result="again")
    other = record_context("Deploy", result="done")

    assert first.index == 0
    assert second.index == 1
    assert other.index == 2
    assert ExecutionRegistry.get_all() == [first, second, other]
    assert ExecutionRegistry.get_by_name("Build") == [first, second]
    assert ExecutionRegistry.get_by_name("missing") == []
    assert ExecutionRegistry._store_by_index == {0: first, 1: second, 2: other}
    assert ExecutionRegistry.get_latest() is other


def test_clear_removes_all_recorded_contexts() -> None:
    record_context("Build", result="ok")

    ExecutionRegistry.clear()

    assert ExecutionRegistry.get_all() == []
    assert ExecutionRegistry.get_by_name("Build") == []
    assert ExecutionRegistry._store_by_index == {}


def test_summary_clear_clears_registry_and_prints_confirmation(
    isolated_registry: CaptureConsole,
) -> None:
    record_context("Build", result="ok")

    ExecutionRegistry.summary(clear=True)

    assert ExecutionRegistry.get_all() == []
    assert "Execution history cleared" in isolated_registry.rendered_text()


def test_summary_last_result_skips_ignored_contexts(
    isolated_registry: CaptureConsole,
) -> None:
    visible = record_context("Visible", result={"answer": 42})
    record_context("Ignored", result="do not show", ignore_in_history=True)

    ExecutionRegistry.summary(last_result=True)

    assert isolated_registry.printed[0][0] == (f"{visible.signature}:",)
    assert isolated_registry.printed[1][0] == (visible.result,)


def test_summary_last_result_prints_traceback_when_latest_visible_context_failed(
    isolated_registry: CaptureConsole,
) -> None:
    failed = record_context("Fail", exception=RuntimeError("boom"), traceback="TRACEBACK")

    ExecutionRegistry.summary(last_result=True)

    assert isolated_registry.printed[0][0] == (f"{failed.signature}:",)
    assert isolated_registry.printed[1][0] == ("TRACEBACK",)


def test_summary_last_result_reports_when_all_contexts_are_ignored(
    isolated_registry: CaptureConsole,
) -> None:
    record_context("Ignored", result="hidden", ignore_in_history=True)

    ExecutionRegistry.summary(last_result=True)

    assert "No valid executions found" in isolated_registry.rendered_text()


def test_summary_result_index_prints_result_for_existing_context(
    isolated_registry: CaptureConsole,
) -> None:
    context = record_context("Build", result=["artifact.whl"])

    ExecutionRegistry.summary(result_index=context.index)

    assert isolated_registry.printed[0][0] == (f"{context.signature}:",)
    assert isolated_registry.printed[1][0] == (context.result,)


def test_summary_result_index_prints_traceback_for_failed_context(
    isolated_registry: CaptureConsole,
) -> None:
    context = record_context("Fail", exception=ValueError("bad"), traceback="STACK")

    ExecutionRegistry.summary(result_index=context.index)

    assert isolated_registry.printed[0][0] == (f"{context.signature}:",)
    assert isolated_registry.printed[1][0] == ("STACK",)


def test_summary_result_index_reports_missing_index(
    isolated_registry: CaptureConsole,
) -> None:
    ExecutionRegistry.summary(result_index=99)

    assert "No execution found for index 99" in isolated_registry.rendered_text()


def test_summary_name_filter_reports_missing_action(
    isolated_registry: CaptureConsole,
) -> None:
    record_context("Build", result="ok")

    ExecutionRegistry.summary(name="Deploy")

    assert "No executions found for action 'Deploy'" in isolated_registry.rendered_text()


def test_summary_name_filter_renders_only_matching_contexts(
    isolated_registry: CaptureConsole,
) -> None:
    record_context("Build", result="ok")
    record_context("Deploy", result="done")
    record_context("Build", result="again")

    ExecutionRegistry.summary(name="Build")

    table = latest_printed_table(isolated_registry)
    assert table.title == "📊 Execution History for 'Build'"
    assert len(table.rows) == 2
    rendered = isolated_registry.rendered_text()
    assert "Build" in rendered
    assert "Deploy" not in rendered


def test_summary_index_filter_renders_existing_context(
    isolated_registry: CaptureConsole,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = record_context("Build", result="ok")
    second = record_context("Deploy", result="done")

    ExecutionRegistry.summary(index=second.index)

    table = latest_printed_table(isolated_registry)
    assert table.title == f"📊 Execution History for Index {second.index}"
    assert len(table.rows) == 1
    rendered = isolated_registry.rendered_text()
    assert "Deploy" in rendered
    assert "Build" not in rendered
    # The implementation currently prints the filtered context list directly.
    assert str([second]) in capsys.readouterr().out
    assert first.index == 0


def test_summary_index_filter_reports_missing_index(
    isolated_registry: CaptureConsole,
) -> None:
    ExecutionRegistry.summary(index=12)

    assert "No execution found for index 12" in isolated_registry.rendered_text()


def test_summary_status_success_filters_out_errors_and_truncates_long_results(
    isolated_registry: CaptureConsole,
) -> None:
    long_result = "x" * 80
    record_context("Success", result=long_result)
    record_context("Failure", exception=RuntimeError("boom"))

    ExecutionRegistry.summary(status="success")

    table = latest_printed_table(isolated_registry)
    assert len(table.rows) == 1
    rendered = isolated_registry.rendered_text()
    assert "Success" in rendered
    assert "Failure" not in rendered
    assert "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx..." in rendered


def test_summary_status_error_filters_out_successes(
    isolated_registry: CaptureConsole,
) -> None:
    record_context("Success", result="ok")
    record_context("Failure", exception=RuntimeError("boom"))

    ExecutionRegistry.summary(status="error")

    table = latest_printed_table(isolated_registry)
    assert len(table.rows) == 1
    rendered = isolated_registry.rendered_text()
    assert "Failure" in rendered
    assert "RuntimeError" in rendered
    assert "Success" not in rendered


def test_summary_uses_na_for_missing_timestamps_and_duration(
    isolated_registry: CaptureConsole,
) -> None:
    record_context("Pending", result=None, start_time=None, end_time=None, duration=None)

    ExecutionRegistry.summary()

    rendered = isolated_registry.rendered_text()
    assert "Pending" in rendered
    assert "n/a" in rendered


def test_summary_defaults_to_all_contexts(
    isolated_registry: CaptureConsole,
) -> None:
    record_context("One", result="ok")
    record_context("Two", exception=RuntimeError("boom"))

    ExecutionRegistry.summary()

    table = latest_printed_table(isolated_registry)
    assert table.title == "📊 Execution History"
    assert len(table.rows) == 2
    rendered = isolated_registry.rendered_text()
    assert "One" in rendered
    assert "Two" in rendered
