"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""

import asyncio
import sys
from argparse import Namespace
from pathlib import Path

from falyx.config import loader
from falyx.falyx import Falyx
from falyx.parsers import FalyxParsers, get_arg_parsers


def find_falyx_config() -> Path | None:
    candidates = [
        Path.cwd() / "falyx.yaml",
        Path.cwd() / "falyx.toml",
        Path.cwd() / ".falyx.yaml",
        Path.home() / ".config" / "falyx" / "falyx.yaml",
        Path.home() / ".falyx.yaml",
    ]
    return next((p for p in candidates if p.exists()), None)


def bootstrap() -> Path | None:
    config_path = find_falyx_config()
    if config_path and str(config_path.parent) not in sys.path:
        sys.path.insert(0, str(config_path.parent))
    return config_path


def parse_args() -> Namespace:
    falyx_parsers: FalyxParsers = get_arg_parsers()
    init_parser = falyx_parsers.subparsers.add_parser(
        "init", help="Create a new Falyx CLI project"
    )
    init_parser.add_argument("name", nargs="?", default=".", help="Project directory")
    falyx_parsers.subparsers.add_parser(
        "init-global", help="Set up ~/.config/falyx with example tasks"
    )

    return falyx_parsers.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "init":
        from falyx.init import init_project

        init_project(args.name)
        return

    if args.command == "init-global":
        from falyx.init import init_global

        init_global()
        return

    bootstrap_path = bootstrap()
    if not bootstrap_path:
        print("No Falyx config file found. Exiting.")
        return None

    flx = Falyx(
        title="🛠️ Config-Driven CLI",
        cli_args=args,
        columns=4,
    )
    flx.add_commands(loader(bootstrap_path))
    asyncio.run(flx.run())


if __name__ == "__main__":
    main()
