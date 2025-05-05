# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
from pathlib import Path

from rich.console import Console

TEMPLATE_TASKS = """\
async def build():
    print("🔨 Building project...")
    return "Build complete!"

async def test():
    print("🧪 Running tests...")
    return "Tests complete!"
"""

TEMPLATE_CONFIG = """\
- key: B
  description: Build the project
  action: tasks.build
  aliases: [build]
  spinner: true

- key: T
  description: Run tests
  action: tasks.test
  aliases: [test]
  spinner: true
"""

console = Console(color_system="auto")


def init_project(name: str = "."):
    target = Path(name).resolve()
    target.mkdir(parents=True, exist_ok=True)

    tasks_path = target / "tasks.py"
    config_path = target / "falyx.yaml"

    if tasks_path.exists() or config_path.exists():
        console.print(f"⚠️  Project already initialized at {target}")
        return

    tasks_path.write_text(TEMPLATE_TASKS)
    config_path.write_text(TEMPLATE_CONFIG)

    print(f"✅ Initialized Falyx project in {target}")


def init_global():
    config_dir = Path.home() / ".config" / "falyx"
    config_dir.mkdir(parents=True, exist_ok=True)

    tasks_path = config_dir / "tasks.py"
    config_path = config_dir / "falyx.yaml"

    if tasks_path.exists() or config_path.exists():
        console.print("⚠️  Global Falyx config already exists at ~/.config/falyx")
        return

    tasks_path.write_text(
        """\
async def cleanup():
    print("🧹 Cleaning temp files...")
"""
    )

    config_path.write_text(
        """\
- key: C
  description: Cleanup temp files
  action: tasks.cleanup
  aliases: [clean, cleanup]
"""
    )

    console.print("✅ Initialized global Falyx config at ~/.config/falyx")
