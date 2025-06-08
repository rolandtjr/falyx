"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""

import asyncio
import os
import sys
from argparse import ArgumentParser, Namespace, _SubParsersAction
from pathlib import Path
from typing import Any

from falyx.config import loader
from falyx.falyx import Falyx
from falyx.parser import CommandArgumentParser, get_root_parser, get_subparsers


def find_falyx_config() -> Path | None:
    candidates = [
        Path.cwd() / "falyx.yaml",
        Path.cwd() / "falyx.toml",
        Path.cwd() / ".falyx.yaml",
        Path.cwd() / ".falyx.toml",
        Path(os.environ.get("FALYX_CONFIG", "falyx.yaml")),
        Path.home() / ".config" / "falyx" / "falyx.yaml",
        Path.home() / ".config" / "falyx" / "falyx.toml",
        Path.home() / ".falyx.yaml",
        Path.home() / ".falyx.toml",
    ]
    return next((p for p in candidates if p.exists()), None)


def bootstrap() -> Path | None:
    config_path = find_falyx_config()
    if config_path and str(config_path.parent) not in sys.path:
        sys.path.insert(0, str(config_path.parent))
    return config_path


def init_config(parser: CommandArgumentParser) -> None:
    parser.add_argument(
        "name",
        type=str,
        help="Name of the new Falyx project",
        default=".",
        nargs="?",
    )


def init_callback(args: Namespace) -> None:
    """Callback for the init command."""
    if args.command == "init":
        from falyx.init import init_project

        init_project(args.name)
    elif args.command == "init_global":
        from falyx.init import init_global

        init_global()


def get_parsers() -> tuple[ArgumentParser, _SubParsersAction]:
    root_parser: ArgumentParser = get_root_parser()
    subparsers = get_subparsers(root_parser)
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a new Falyx project",
        description="Create a new Falyx project with mock configuration files.",
        epilog="If no name is provided, the current directory will be used.",
    )
    init_parser.add_argument(
        "name",
        type=str,
        help="Name of the new Falyx project",
        default=".",
        nargs="?",
    )
    subparsers.add_parser(
        "init-global",
        help="Initialize Falyx global configuration",
        description="Create a global Falyx configuration at ~/.config/falyx/.",
    )
    return root_parser, subparsers


def main() -> Any:
    bootstrap_path = bootstrap()
    if not bootstrap_path:
        from falyx.init import init_global, init_project

        flx: Falyx = Falyx()
        flx.add_command(
            "I",
            "Initialize a new Falyx project",
            init_project,
            aliases=["init"],
            argument_config=init_config,
            help_epilog="If no name is provided, the current directory will be used.",
        )
        flx.add_command(
            "G",
            "Initialize Falyx global configuration",
            init_global,
            aliases=["init-global"],
            help_text="Create a global Falyx configuration at ~/.config/falyx/.",
        )
    else:
        flx = loader(bootstrap_path)

    root_parser, subparsers = get_parsers()

    return asyncio.run(
        flx.run(root_parser=root_parser, subparsers=subparsers, callback=init_callback)
    )


if __name__ == "__main__":
    main()
