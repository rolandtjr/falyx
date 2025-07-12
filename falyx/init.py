# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""init.py"""
from pathlib import Path

from falyx.console import console

TEMPLATE_TASKS = """\
# This file is used by falyx.yaml to define CLI actions.
# You can run: falyx run [key] or falyx list to see available commands.

import asyncio
import json

from falyx.action import Action, ChainedAction, ShellAction, SelectionAction


post_ids = ["1", "2", "3", "4", "5"]

pick_post = SelectionAction(
    name="Pick Post ID",
    selections=post_ids,
    title="Choose a Post ID",
    prompt_message="Select a post > ",
)

fetch_post = ShellAction(
    name="Fetch Post via curl",
    command_template="curl https://jsonplaceholder.typicode.com/posts/{}",
)

async def get_post_title(last_result):
    return json.loads(last_result).get("title", "No title found")

post_flow = ChainedAction(
    name="Fetch and Parse Post",
    actions=[pick_post, fetch_post, get_post_title],
    auto_inject=True,
)

async def hello():
    print("👋 Hello from Falyx!")
    return "Hello Complete!"

async def some_work():
    await asyncio.sleep(2)
    print("Work Finished!")
    return "Work Complete!"

work_action = Action(
    name="Work Action",
    action=some_work,
)
"""

TEMPLATE_CONFIG = """\
# falyx.yaml — Config-driven CLI definition
# Define your commands here and point to Python callables in tasks.py
title: Sample CLI Project
prompt:
  - ["#61AFEF bold", "FALYX > "]
columns: 3
welcome_message: "🚀 Welcome to your new CLI project!"
exit_message: "👋 See you next time!"
commands:
  - key: S
    description: Say Hello
    action: tasks.hello
    aliases: [hi, hello]
    tags: [example]

  - key: P
    description: Get Post Title
    action: tasks.post_flow
    aliases: [submit]
    preview_before_confirm: true
    confirm: true
    tags: [demo, network]

  - key: G
    description: Do Some Work
    action: tasks.work_action
    aliases: [work]
    spinner: true
    spinner_message: "Working..."
"""

GLOBAL_TEMPLATE_TASKS = """\
async def cleanup():
    print("🧹 Cleaning temp files...")
"""

GLOBAL_CONFIG = """\
title: Global Falyx Config
commands:
  - key: C
    description: Cleanup temp files
    action: tasks.cleanup
    aliases: [clean, cleanup]
"""


def init_project(name: str) -> None:
    target = Path(name).resolve()
    target.mkdir(parents=True, exist_ok=True)

    tasks_path = target / "tasks.py"
    config_path = target / "falyx.yaml"

    if tasks_path.exists() or config_path.exists():
        console.print(f"⚠️  Project already initialized at {target}")
        return None

    tasks_path.write_text(TEMPLATE_TASKS)
    config_path.write_text(TEMPLATE_CONFIG)

    console.print(f"✅ Initialized Falyx project in {target}")


def init_global() -> None:
    config_dir = Path.home() / ".config" / "falyx"
    config_dir.mkdir(parents=True, exist_ok=True)

    tasks_path = config_dir / "tasks.py"
    config_path = config_dir / "falyx.yaml"

    if tasks_path.exists() or config_path.exists():
        console.print("⚠️  Global Falyx config already exists at ~/.config/falyx")
        return None

    tasks_path.write_text(GLOBAL_TEMPLATE_TASKS)
    config_path.write_text(GLOBAL_CONFIG)

    console.print("✅ Initialized global Falyx config at ~/.config/falyx")
