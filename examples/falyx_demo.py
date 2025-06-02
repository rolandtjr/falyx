"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""

import asyncio
import random
from argparse import Namespace

from falyx.action import Action, ActionGroup, ChainedAction
from falyx.falyx import Falyx
from falyx.parsers import FalyxParsers, get_arg_parsers
from falyx.version import __version__


class Foo:
    def __init__(self, flx: Falyx) -> None:
        self.flx = flx

    async def build(self):
        await asyncio.sleep(1)
        print("✅ Build complete!")
        return "Build complete!"

    async def test(self):
        await asyncio.sleep(1)
        print("✅ Tests passed!")
        return "Tests passed!"

    async def deploy(self):
        await asyncio.sleep(1)
        print("✅ Deployment complete!")
        return "Deployment complete!"

    async def clean(self):
        print("🧹 Cleaning...")
        await asyncio.sleep(1)
        print("✅ Clean complete!")
        return "Clean complete!"

    async def build_package(self):
        print("🔨 Building...")
        await asyncio.sleep(1)
        print("✅ Build finished!")
        return "Build finished!"

    async def package(self):
        print("📦 Packaging...")
        await asyncio.sleep(1)
        print("✅ Package complete!")
        return "Package complete!"

    async def run_tests(self):
        print("🧪 Running tests...")
        await asyncio.sleep(random.randint(1, 3))
        print("✅ Tests passed!")
        return "Tests passed!"

    async def run_integration_tests(self):
        print("🔗 Running integration tests...")
        await asyncio.sleep(random.randint(1, 3))
        print("✅ Integration tests passed!")
        return "Integration tests passed!"

    async def run_linter(self):
        print("🧹 Running linter...")
        await asyncio.sleep(random.randint(1, 3))
        print("✅ Linter passed!")
        return "Linter passed!"

    async def run(self):
        await self.flx.run()


async def main() -> None:
    """Build and return a Falyx instance with all your commands."""
    flx = Falyx(
        title="🚀 Falyx CLI",
        columns=5,
        welcome_message="Welcome to Falyx CLI!",
        exit_message="Goodbye!",
    )
    foo = Foo(flx)

    # --- Bottom bar info ---
    flx.bottom_bar.columns = 3
    flx.bottom_bar.add_toggle_from_option("V", "Verbose", flx.options, "verbose")
    flx.bottom_bar.add_toggle_from_option("U", "Debug Hooks", flx.options, "debug_hooks")
    flx.bottom_bar.add_static("Version", f"Falyx v{__version__}")

    # --- Command actions ---

    # --- Single Actions ---
    flx.add_command(
        key="B",
        description="Build project",
        action=Action("Build", foo.build),
        tags=["build"],
        spinner=True,
        spinner_message="📦 Building...",
    )
    flx.add_command(
        key="T",
        description="Run tests",
        action=Action("Test", foo.test),
        tags=["test"],
        spinner=True,
        spinner_message="🧪 Running tests...",
    )
    flx.add_command(
        key="D",
        description="Deploy project",
        action=Action("Deploy", foo.deploy),
        tags=["deploy"],
        spinner=True,
        spinner_message="🚀 Deploying...",
    )

    # --- Build pipeline (ChainedAction) ---
    pipeline = ChainedAction(
        name="Full Build Pipeline",
        actions=[
            Action("Clean", foo.clean),
            Action("Build", foo.build_package),
            Action("Package", foo.package),
        ],
    )
    flx.add_command(
        key="P",
        description="Run Build Pipeline",
        action=pipeline,
        tags=["build", "pipeline"],
        spinner=True,
        spinner_message="🔨 Running build pipeline...",
        spinner_type="line",
    )

    # --- Test suite (ActionGroup) ---
    test_suite = ActionGroup(
        name="Test Suite",
        actions=[
            Action("Unit Tests", foo.run_tests),
            Action("Integration Tests", foo.run_integration_tests),
            Action("Lint", foo.run_linter),
        ],
    )
    flx.add_command(
        key="G",
        description="Run All Tests",
        action=test_suite,
        tags=["test", "parallel"],
        spinner=True,
        spinner_type="line",
    )
    await foo.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        pass
