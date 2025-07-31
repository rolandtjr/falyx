# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Centralized spinner rendering for Falyx CLI.

This module provides the `SpinnerManager` class, which manages a collection of
Rich spinners that can be displayed concurrently during long-running tasks.

Key Features:
    • Automatic lifecycle management:
        - Starts a single Rich `Live` loop when the first spinner is added.
        - Stops and clears the display when the last spinner is removed.
    • Thread/async-safe start logic via a lightweight lock to prevent
      duplicate Live loops from being launched.
    • Supports multiple spinners running simultaneously, each with its own
      text, style, type, and speed.
    • Integrates with Falyx's OptionsManager so actions and commands can
      declaratively request spinners without directly managing terminal state.

Classes:
    SpinnerData:
        Lightweight container for individual spinner settings (message,
        type, style, speed) and its underlying Rich `Spinner` object.
    SpinnerManager:
        Manages all active spinners, handles Live rendering, and provides
        methods to add, update, and remove spinners.

Example:
    ```python
    >>> manager = SpinnerManager()
    >>> await manager.add("build", "Building project…", spinner_type="dots")
    >>> await manager.add("deploy", "Deploying to AWS…", spinner_type="earth")
    # Both spinners animate in one unified Live panel
    >>> manager.remove("build")
    >>> manager.remove("deploy")
    ```

Design Notes:
    • SpinnerManager should only create **one** Live loop at a time.
    • When no spinners remain, the Live panel is cleared (`transient=True`)
      so the CLI output returns to a clean state.
    • Hooks in `falyx.hooks` (spinner_before_hook / spinner_teardown_hook)
      call into this manager automatically when `spinner=True` is set on
      an Action or Command.
"""

import asyncio

from rich.console import Group
from rich.live import Live
from rich.spinner import Spinner

from falyx.console import console
from falyx.logger import logger
from falyx.themes import OneColors


class SpinnerData:
    """
    Holds the configuration and Rich spinner object for a single task.

    This class is a lightweight container for spinner metadata, storing the
    message text, spinner type, style, and speed. It also initializes the
    corresponding Rich `Spinner` instance used by `SpinnerManager` for
    rendering.

    Attributes:
        text (str): The message displayed next to the spinner.
        spinner_type (str): The Rich spinner preset to use (e.g., "dots",
            "bouncingBall", "earth").
        spinner_style (str): Rich color/style for the spinner animation.
        spinner (Spinner): The instantiated Rich spinner object.

    Example:
        ```
        >>> data = SpinnerData("Deploying...", spinner_type="earth",
        ...                    spinner_style="cyan", spinner_speed=1.0)
        >>> data.spinner
        <rich.spinner.Spinner object ...>
        ```
    """

    def __init__(
        self, text: str, spinner_type: str, spinner_style: str, spinner_speed: float
    ):
        """Initialize a spinner with text, type, style, and speed."""
        self.text = text
        self.spinner_type = spinner_type
        self.spinner_style = spinner_style
        self.spinner = Spinner(
            spinner_type, text=text, style=spinner_style, speed=spinner_speed
        )


class SpinnerManager:
    """
    Manages multiple Rich spinners and handles their terminal rendering.

    SpinnerManager maintains a registry of active spinners and a single
    Rich `Live` display loop to render them. When the first spinner is added,
    the Live loop starts automatically. When the last spinner is removed,
    the Live loop stops and the panel clears (via `transient=True`).

    This class is designed for integration with Falyx's `OptionsManager`
    so any Action or Command can declaratively register spinners without
    directly controlling terminal state.

    Key Behaviors:
        • Starts exactly one `Live` loop, protected by a start lock to prevent
          duplicate launches in async/threaded contexts.
        • Supports multiple simultaneous spinners, each with independent
          text, style, and type.
        • Clears the display when all spinners are removed.

    Attributes:
        console (Console): The Rich console used for rendering.
        _spinners (dict[str, SpinnerData]): Internal store of active spinners.
        _task (asyncio.Task | None): The running Live loop task, if any.
        _running (bool): Indicates if the Live loop is currently active.

    Example:
        ```
        >>> manager = SpinnerManager()
        >>> await manager.add("build", "Building project…")
        >>> await manager.add("deploy", "Deploying services…", spinner_type="earth")
        >>> manager.remove("build")
        >>> manager.remove("deploy")
        ```
    """

    def __init__(self) -> None:
        """Initialize the SpinnerManager with an empty spinner registry."""
        self.console = console
        self._spinners: dict[str, SpinnerData] = {}
        self._task: asyncio.Task | None = None
        self._running: bool = False

        self._lock = asyncio.Lock()

    async def add(
        self,
        name: str,
        text: str,
        spinner_type: str = "dots",
        spinner_style: str = OneColors.CYAN,
        spinner_speed: float = 1.0,
    ):
        """Add a new spinner and start the Live loop if not already running."""
        self._spinners[name] = SpinnerData(
            text=text,
            spinner_type=spinner_type,
            spinner_style=spinner_style,
            spinner_speed=spinner_speed,
        )
        async with self._lock:
            if not self._running:
                logger.debug("[%s] Starting spinner manager Live loop.", name)
                await self._start_live()

    def update(
        self,
        name: str,
        text: str | None = None,
        spinner_type: str | None = None,
        spinner_style: str | None = None,
    ):
        """Update an existing spinner's message, style, or type."""
        if name in self._spinners:
            data = self._spinners[name]
            if text:
                data.text = text
                data.spinner.text = text
            if spinner_style:
                data.spinner_style = spinner_style
                data.spinner.style = spinner_style
            if spinner_type:
                data.spinner_type = spinner_type
                data.spinner = Spinner(spinner_type, text=data.text)

    async def remove(self, name: str):
        """Remove a spinner and stop the Live loop if no spinners remain."""
        self._spinners.pop(name, None)
        async with self._lock:
            if not self._spinners:
                logger.debug("[%s] Stopping spinner manager, no spinners left.", name)
                if self._task:
                    self._task.cancel()
                self._running = False

    async def _start_live(self):
        """Start the Live rendering loop in the background."""
        self._running = True
        self._task = asyncio.create_task(self._live_loop())

    def render_panel(self):
        """Render all active spinners as a grouped Rich panel."""
        rows = []
        for data in self._spinners.values():
            rows.append(data.spinner)
        return Group(*rows)

    async def _live_loop(self):
        """Continuously refresh the spinner display until stopped."""
        with Live(
            self.render_panel(),
            refresh_per_second=12.5,
            console=self.console,
            transient=True,
        ) as live:
            while self._spinners:
                live.update(self.render_panel())
                await asyncio.sleep(0.1)


if __name__ == "__main__":
    spinner_manager = SpinnerManager()

    async def demo():
        # Add multiple spinners
        await spinner_manager.add("task1", "Loading configs…")
        await spinner_manager.add(
            "task2", "Building containers…", spinner_type="bouncingBall"
        )
        await spinner_manager.add("task3", "Deploying services…", spinner_type="earth")

        # Simulate work
        await asyncio.sleep(2)
        spinner_manager.update("task1", text="Configs loaded ✅")
        await asyncio.sleep(1)
        spinner_manager.remove("task1")

        await spinner_manager.add("task4", "Running Tests...")

        await asyncio.sleep(2)
        spinner_manager.update("task2", text="Build complete ✅")
        spinner_manager.remove("task2")

        await asyncio.sleep(1)
        spinner_manager.update("task3", text="Deployed! 🎉")
        await asyncio.sleep(1)
        spinner_manager.remove("task3")

        await asyncio.sleep(5)

        spinner_manager.update("task4", "Tests Complete!")
        spinner_manager.remove("task4")
        console.print("Done!")

    asyncio.run(demo())
