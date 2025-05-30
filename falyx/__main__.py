"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from falyx.config import loader
from falyx.falyx import Falyx
from falyx.parsers import CommandArgumentParser


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
        )
        flx.add_command(
            "G",
            "Initialize Falyx global configuration",
            init_global,
            aliases=["init-global"],
        )
    else:
        flx = loader(bootstrap_path)

    return asyncio.run(flx.run())


if __name__ == "__main__":
    main()
