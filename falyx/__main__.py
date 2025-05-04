"""
Falyx CLI Framework

Copyright (c) 2025 rtj.dev LLC.
Licensed under the MIT License. See LICENSE file for details.
"""

import asyncio
import sys
from pathlib import Path

from falyx.config import loader
from falyx.falyx import Falyx
from falyx.parsers import get_arg_parsers


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


def main() -> None:
    bootstrap_path = bootstrap()
    if not bootstrap_path:
        print("No Falyx config file found. Exiting.")
        return None
    args = get_arg_parsers().parse_args()
    flx = Falyx(
        title="🛠️ Config-Driven CLI",
        cli_args=args,
        columns=4,
    )
    flx.add_commands(loader(bootstrap_path))
    asyncio.run(flx.run())


if __name__ == "__main__":
    main()
