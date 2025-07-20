# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Provides the `ExecutionRegistry`, a centralized runtime store for capturing and inspecting
the execution history of Falyx actions.

The registry automatically records every `ExecutionContext` created during action
execution—including context metadata, results, exceptions, duration, and tracebacks.
It supports filtering, summarization, and visual inspection via a Rich-rendered table.

Designed for:
- Workflow debugging and CLI diagnostics
- Interactive history browsing or replaying previous runs
- Providing user-visible `history` or `last-result` commands inside CLI apps

Key Features:
- Global, in-memory store of all `ExecutionContext` objects (by name, index, or full list)
- Thread-safe indexing and summary display
- Traceback-aware result inspection and filtering by status (success/error)
- Used by built-in `History` command in Falyx CLI

Example:
    from falyx.execution_registry import ExecutionRegistry as er

    # Record a context
    er.record(context)

    # Display a rich table summary
    er.summary()

    # Print the last non-ignored result
    er.summary(last_result=True)

    # Clear execution history
    er.summary(clear=True)

Note:
    The registry is volatile and cleared on each process restart or when `clear()` is called.
    All data is retained in memory only.

Public Interface:
- record(context): Log an ExecutionContext and assign index.
- get_all(): List all stored contexts.
- get_by_name(name): Retrieve all contexts by action name.
- get_latest(): Retrieve the most recent context.
- clear(): Reset the registry.
- summary(...): Rich console summary of stored execution results.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from threading import Lock
from typing import Literal

from rich import box
from rich.console import Console
from rich.table import Table

from falyx.console import console
from falyx.context import ExecutionContext
from falyx.logger import logger
from falyx.themes import OneColors


class ExecutionRegistry:
    """
    Global registry for recording and inspecting Falyx action executions.

    This class captures every `ExecutionContext` created by Falyx Actions,
    tracking metadata, results, exceptions, and performance metrics. It enables
    rich introspection, post-execution inspection, and formatted summaries
    suitable for interactive and headless CLI use.

    Data is retained in memory until cleared or process exit.

    Use Cases:
        - Auditing chained or dynamic workflows
        - Rendering execution history in a help/debug menu
        - Accessing previous results or errors for reuse

    Attributes:
        _store_by_name (dict): Maps action name → list of ExecutionContext objects.
        _store_by_index (dict): Maps numeric index → ExecutionContext.
        _store_all (list): Ordered list of all contexts.
        _index (int): Global counter for assigning unique execution indices.
        _lock (Lock): Thread lock for atomic writes to the registry.
        _console (Console): Rich console used for rendering summaries.
    """

    _store_by_name: dict[str, list[ExecutionContext]] = defaultdict(list)
    _store_by_index: dict[int, ExecutionContext] = {}
    _store_all: list[ExecutionContext] = []
    _console: Console = console
    _index = 0
    _lock = Lock()

    @classmethod
    def record(cls, context: ExecutionContext):
        """
        Record an execution context and assign a unique index.

        This method logs the context, appends it to the registry,
        and makes it available for future summary or filtering.

        Args:
            context (ExecutionContext): The context to be tracked.
        """
        logger.debug(context.to_log_line())
        with cls._lock:
            context.index = cls._index
            cls._store_by_index[cls._index] = context
            cls._index += 1
        cls._store_by_name[context.name].append(context)
        cls._store_all.append(context)

    @classmethod
    def get_all(cls) -> list[ExecutionContext]:
        """
        Return all recorded execution contexts in order of execution.

        Returns:
            list[ExecutionContext]: All stored action contexts.
        """
        return cls._store_all

    @classmethod
    def get_by_name(cls, name: str) -> list[ExecutionContext]:
        """
        Retrieve all executions recorded under a given action name.

        Args:
            name (str): The name of the action.

        Returns:
            list[ExecutionContext]: Matching contexts, or empty if none found.
        """
        return cls._store_by_name.get(name, [])

    @classmethod
    def get_latest(cls) -> ExecutionContext:
        """
        Return the most recent execution context.

        Returns:
            ExecutionContext: The last recorded context.
        """
        return cls._store_all[-1]

    @classmethod
    def clear(cls):
        """
        Clear all stored execution data and reset internal indices.

        This operation is destructive and cannot be undone.
        """
        cls._store_by_name.clear()
        cls._store_all.clear()
        cls._store_by_index.clear()

    @classmethod
    def summary(
        cls,
        name: str = "",
        index: int | None = None,
        result_index: int | None = None,
        clear: bool = False,
        last_result: bool = False,
        status: Literal["all", "success", "error"] = "all",
    ):
        """
        Display a formatted Rich table of recorded executions.

        Supports filtering by action name, index, or execution status.
        Can optionally show only the last result or a specific indexed result.
        Also supports clearing the registry interactively.

        Args:
            name (str): Filter by action name.
            index (int | None): Filter by specific execution index.
            result_index (int | None): Print result (or traceback) of a specific index.
            clear (bool): If True, clears the registry and exits.
            last_result (bool): If True, prints only the most recent result.
            status (Literal): One of "all", "success", or "error" to filter displayed rows.
        """
        if clear:
            cls.clear()
            cls._console.print(f"[{OneColors.GREEN}]✅ Execution history cleared.")
            return

        if last_result:
            for ctx in reversed(cls._store_all):
                if not ctx.action.ignore_in_history:
                    cls._console.print(f"{ctx.signature}:")
                    if ctx.traceback:
                        cls._console.print(ctx.traceback)
                    else:
                        cls._console.print(ctx.result)
                    return
            cls._console.print(
                f"[{OneColors.DARK_RED}]❌ No valid executions found to display last result."
            )
            return

        if result_index is not None and result_index >= 0:
            try:
                result_context = cls._store_by_index[result_index]
            except KeyError:
                cls._console.print(
                    f"[{OneColors.DARK_RED}]❌ No execution found for index {result_index}."
                )
                return
            cls._console.print(f"{result_context.signature}:")
            if result_context.traceback:
                cls._console.print(result_context.traceback)
            else:
                cls._console.print(result_context.result)
            return

        if name:
            contexts = cls.get_by_name(name)
            if not contexts:
                cls._console.print(
                    f"[{OneColors.DARK_RED}]❌ No executions found for action '{name}'."
                )
                return
            title = f"📊 Execution History for '{contexts[0].name}'"
        elif index is not None and index >= 0:
            try:
                contexts = [cls._store_by_index[index]]
                print(contexts)
            except KeyError:
                cls._console.print(
                    f"[{OneColors.DARK_RED}]❌ No execution found for index {index}."
                )
                return
            title = f"📊 Execution History for Index {index}"
        else:
            contexts = cls.get_all()
            title = "📊 Execution History"

        table = Table(title=title, expand=True, box=box.SIMPLE)

        table.add_column("Index", justify="right", style="dim")
        table.add_column("Name", style="bold cyan")
        table.add_column("Start", justify="right", style="dim")
        table.add_column("End", justify="right", style="dim")
        table.add_column("Duration", justify="right")
        table.add_column("Status", style="bold")
        table.add_column("Result / Exception", overflow="fold")

        for ctx in contexts:
            start = (
                datetime.fromtimestamp(ctx.start_time).strftime("%H:%M:%S")
                if ctx.start_time
                else "n/a"
            )
            end = (
                datetime.fromtimestamp(ctx.end_time).strftime("%H:%M:%S")
                if ctx.end_time
                else "n/a"
            )
            duration = f"{ctx.duration:.3f}s" if ctx.duration else "n/a"

            if ctx.exception and status.lower() in ["all", "error"]:
                final_status = f"[{OneColors.DARK_RED}]❌ Error"
                final_result = repr(ctx.exception)
            elif status.lower() in ["all", "success"]:
                final_status = f"[{OneColors.GREEN}]✅ Success"
                final_result = repr(ctx.result)
                if len(final_result) > 50:
                    final_result = f"{final_result[:50]}..."
            else:
                continue

            table.add_row(
                str(ctx.index), ctx.name, start, end, duration, final_status, final_result
            )

        cls._console.print(table)
