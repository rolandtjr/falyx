# falyx/__main__.py

import asyncio
import logging

from falyx.action import Action
from falyx.falyx import Falyx


def build_falyx() -> Falyx:
    """Build and return a Falyx instance with all your commands."""
    app = Falyx(title="🚀 Falyx CLI")

    # Example commands
    app.add_command(
        key="B",
        description="Build project",
        action=Action("Build", lambda: print("📦 Building...")),
        tags=["build"]
    )

    app.add_command(
        key="T",
        description="Run tests",
        action=Action("Test", lambda: print("🧪 Running tests...")),
        tags=["test"]
    )

    app.add_command(
        key="D",
        description="Deploy project",
        action=Action("Deploy", lambda: print("🚀 Deploying...")),
        tags=["deploy"]
    )

    return app

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    falyx = build_falyx()
    asyncio.run(falyx.cli())
