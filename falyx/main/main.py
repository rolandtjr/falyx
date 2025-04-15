import asyncio
import logging
from rich.markdown import Markdown

from falyx import Action, Falyx, HookType
from falyx.hooks import log_before, log_success, log_error, log_after
from falyx.themes.colors import OneColors
from falyx.utils import setup_logging

# Setup logging
setup_logging(console_log_level=logging.WARNING, json_log_to_file=True)


def main():
    # Create the menu
    menu = Falyx(
        title=Markdown("# 🚀 Falyx CLI Demo"),
        welcome_message="Welcome to Falyx!",
        exit_message="Thanks for using Falyx!",
        include_history_command=True,
        include_help_command=True,
    )

    # Define async actions
    async def hello():
        print("👋 Hello from Falyx CLI!")

    def goodbye():
        print("👋 Goodbye from Falyx CLI!")

    async def do_task_and_increment(counter_name: str = "tasks"):
        await asyncio.sleep(3)
        print("✅ Task completed.")
        menu.bottom_bar.increment_total_counter(counter_name)

    # Register global logging hooks
    menu.hooks.register(HookType.BEFORE, log_before)
    menu.hooks.register(HookType.ON_SUCCESS, log_success)
    menu.hooks.register(HookType.ON_ERROR, log_error)
    menu.hooks.register(HookType.AFTER, log_after)

    # Add a toggle to the bottom bar
    menu.add_toggle("D", "Debug Mode", state=False)

    # Add a counter to the bottom bar
    menu.add_total_counter("tasks", "Tasks", current=0, total=5)

    # Add static text to the bottom bar
    menu.add_static("env", "🌐 Local Env")

    # Add commands with help_text
    menu.add_command(
        key="S",
        description="Say Hello",
        help_text="Greets the user with a friendly hello message.",
        action=Action("Hello", hello),
        color=OneColors.CYAN,
    )

    menu.add_command(
        key="G",
        description="Say Goodbye",
        help_text="Bids farewell and thanks the user for using the app.",
        action=Action("Goodbye", goodbye),
        color=OneColors.MAGENTA,
    )

    menu.add_command(
        key="T",
        description="Run a Task",
        aliases=["task", "run"],
        help_text="Performs a task and increments the counter by 1.",
        action=do_task_and_increment,
        args=("tasks",),
        color=OneColors.GREEN,
        spinner=True,
    )

    asyncio.run(menu.cli())


if __name__ == "__main__":
    """
    Entry point for the Falyx CLI demo application.
    This function initializes the menu and runs it.
    """
    main()