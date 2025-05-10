# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""execution_registry.py"""
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from rich import box
from rich.console import Console
from rich.table import Table

from falyx.context import ExecutionContext
from falyx.utils import logger


class ExecutionRegistry:
    _store_by_name: Dict[str, List[ExecutionContext]] = defaultdict(list)
    _store_all: List[ExecutionContext] = []
    _console = Console(color_system="auto")

    @classmethod
    def record(cls, context: ExecutionContext):
        """Record an execution context."""
        logger.debug(context.to_log_line())
        cls._store_by_name[context.name].append(context)
        cls._store_all.append(context)

    @classmethod
    def get_all(cls) -> List[ExecutionContext]:
        return cls._store_all

    @classmethod
    def get_by_name(cls, name: str) -> List[ExecutionContext]:
        return cls._store_by_name.get(name, [])

    @classmethod
    def get_latest(cls) -> ExecutionContext:
        return cls._store_all[-1]

    @classmethod
    def clear(cls):
        cls._store_by_name.clear()
        cls._store_all.clear()

    @classmethod
    def summary(cls):
        table = Table(title="[📊] Execution History", expand=True, box=box.SIMPLE)

        table.add_column("Name", style="bold cyan")
        table.add_column("Start", justify="right", style="dim")
        table.add_column("End", justify="right", style="dim")
        table.add_column("Duration", justify="right")
        table.add_column("Status", style="bold")
        table.add_column("Result / Exception", overflow="fold")

        for ctx in cls.get_all():
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

            if ctx.exception:
                status = "[bold red]❌ Error"
                result = repr(ctx.exception)
            else:
                status = "[green]✅ Success"
                result = repr(ctx.result)
                if len(result) > 1000:
                    result = f"{result[:1000]}..."

            table.add_row(ctx.name, start, end, duration, status, result)

        cls._console.print(table)

    @classmethod
    def get_history_action(cls) -> "Action":
        """Return an Action that prints the execution summary."""
        from falyx.action import Action

        async def show_history():
            cls.summary()

        return Action(name="View Execution History", action=show_history)
