"""scripts/sync_version.py"""

from pathlib import Path

import toml


def main():
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    version_path = Path(__file__).parent.parent / "falyx" / "version.py"

    data = toml.load(pyproject_path)
    version = data["tool"]["poetry"]["version"]

    version_path.write_text(f'__version__ = "{version}"\n')
    print(f"✅ Synced version: {version} → {version_path}")


if __name__ == "__main__":
    main()
