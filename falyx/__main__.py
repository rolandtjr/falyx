"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""
import asyncio

from falyx.action import Action, ActionGroup, ChainedAction
from falyx.falyx import Falyx


def build_falyx() -> Falyx:
    """Build and return a Falyx instance with all your commands."""
    flx = Falyx(title="🚀 Falyx CLI")

    # Example commands
    flx.add_command(
        key="B",
        description="Build project",
        action=Action("Build", lambda: print("📦 Building...")),
        tags=["build"]
    )

    flx.add_command(
        key="T",
        description="Run tests",
        action=Action("Test", lambda: print("🧪 Running tests...")),
        tags=["test"]
    )

    flx.add_command(
        key="D",
        description="Deploy project",
        action=Action("Deploy", lambda: print("🚀 Deploying...")),
        tags=["deploy"]
    )

    # Example of ChainedAction (pipeline)
    build_pipeline = ChainedAction(
        name="Full Build Pipeline",
        actions=[
            Action("Clean", lambda: print("🧹 Cleaning...")),
            Action("Build", lambda: print("🔨 Building...")),
            Action("Package", lambda: print("📦 Packaging...")),
        ],
        auto_inject=False,
    )
    flx.add_command(
        key="P",
        description="Run Build Pipeline",
        action=build_pipeline,
        tags=["build", "pipeline"]
    )

    # Example of ActionGroup (parallel tasks)
    test_suite = ActionGroup(
        name="Test Suite",
        actions=[
            Action("Unit Tests", lambda: print("🧪 Running unit tests...")),
            Action("Integration Tests", lambda: print("🔗 Running integration tests...")),
            Action("Lint", lambda: print("🧹 Running linter...")),
        ]
    )
    flx.add_command(
        key="G",
        description="Run All Tests",
        action=test_suite,
        tags=["test", "parallel"]
    )

    return flx

if __name__ == "__main__":
    flx = build_falyx()
    asyncio.run(flx.run())

