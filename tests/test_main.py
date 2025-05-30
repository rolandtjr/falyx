import os
import shutil
import sys
from pathlib import Path

import pytest

from falyx.__main__ import bootstrap, find_falyx_config, main


def test_find_falyx_config():
    """Test if the falyx config file is found correctly."""

    config_file = Path("falyx.yaml").resolve()
    config_file.touch()
    config_path = find_falyx_config()
    assert config_path == config_file
    config_file.unlink()


def test_bootstrap():
    """Test if the bootstrap function works correctly."""
    config_file = Path("falyx.yaml").resolve()
    config_file.touch()
    sys_path_before = list(sys.path)
    bootstrap_path = bootstrap()
    assert bootstrap_path == config_file
    assert str(config_file.parent) in sys.path
    config_file.unlink()
    sys.path = sys_path_before


def test_bootstrap_no_config():
    """Test if the bootstrap function works correctly when no config file is found."""
    sys_path_before = list(sys.path)
    bootstrap_path = bootstrap()
    assert bootstrap_path is None
    assert sys.path == sys_path_before
    # assert str(Path.cwd()) not in sys.path


def test_bootstrap_with_global_config():
    """Test if the bootstrap function works correctly when a global config file is found."""
    config_file = Path.home() / ".config" / "falyx" / "falyx.yaml"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.touch()
    sys_path_before = list(sys.path)
    bootstrap_path = bootstrap()
    assert bootstrap_path == config_file
    assert str(config_file.parent) in sys.path
    config_file.unlink()
    sys.path = sys_path_before
