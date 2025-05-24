import asyncio
import time

from falyx import Falyx
from falyx.action import (
    Action,
    ActionGroup,
    ChainedAction,
    MenuAction,
    ProcessAction,
    PromptMenuAction,
)
from falyx.menu import MenuOption, MenuOptionMap
from falyx.themes import OneColors


# Basic coroutine for Action
async def greet_user():
    print("👋 Hello from a regular Action!")
    await asyncio.sleep(0.5)
    return "Greeted user."


# Chain of tasks
async def fetch_data():
    print("📡 Fetching data...")
    await asyncio.sleep(1)
    return "data123"


async def process_data(last_result):
    print(f"⚙️ Processing: {last_result}")
    await asyncio.sleep(1)
    return f"processed({last_result})"


async def save_data(last_result):
    print(f"💾 Saving: {last_result}")
    await asyncio.sleep(1)
    return f"saved({last_result})"


# Parallel tasks
async def fetch_users():
    print("👥 Fetching users...")
    await asyncio.sleep(1)
    return ["alice", "bob", "carol"]


async def fetch_logs():
    print("📝 Fetching logs...")
    await asyncio.sleep(2)
    return ["log1", "log2"]


# CPU-bound task (simulate via blocking sleep)
def heavy_computation():
    print("🧠 Starting heavy computation...")
    time.sleep(3)
    print("✅ Finished computation.")
    return 42


# Define actions

basic_action = Action("greet", greet_user)

chained = ChainedAction(
    name="data-pipeline",
    actions=[
        Action("fetch", fetch_data),
        Action("process", process_data, inject_last_result=True),
        Action("save", save_data, inject_last_result=True),
    ],
    auto_inject=True,
)

parallel = ActionGroup(
    name="parallel-fetch",
    actions=[
        Action("fetch-users", fetch_users),
        Action("fetch-logs", fetch_logs),
    ],
)

process = ProcessAction(name="compute", action=heavy_computation)

menu_options = MenuOptionMap(
    {
        "A": MenuOption("Run basic Action", basic_action, style=OneColors.LIGHT_YELLOW),
        "C": MenuOption("Run ChainedAction", chained, style=OneColors.MAGENTA),
        "P": MenuOption("Run ActionGroup (parallel)", parallel, style=OneColors.CYAN),
        "H": MenuOption("Run ProcessAction (heavy task)", process, style=OneColors.GREEN),
    }
)


# Menu setup

menu = MenuAction(
    name="main-menu",
    title="Choose a task to run",
    menu_options=menu_options,
)


prompt_menu = PromptMenuAction(
    name="select-user",
    menu_options=menu_options,
)

flx = Falyx(
    title="🚀 Falyx Menu Demo",
    welcome_message="Welcome to the Menu Demo!",
    exit_message="Goodbye!",
    columns=2,
    never_prompt=False,
)

flx.add_command(
    key="M",
    description="Show Menu",
    action=menu,
    logging_hooks=True,
)

flx.add_command(
    key="P",
    description="Show Prompt Menu",
    action=prompt_menu,
    logging_hooks=True,
)


if __name__ == "__main__":
    asyncio.run(flx.run())
