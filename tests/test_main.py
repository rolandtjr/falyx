import os
import shutil
import sys
from pathlib import Path

import pytest

from falyx.__main__ import bootstrap, find_falyx_config, get_falyx_parsers, run


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
    assert str(Path.cwd()) in sys.path
    sys.path = sys_path_before


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


def test_parse_args():
    """Test if the parse_args function works correctly."""
    falyx_parsers = get_falyx_parsers()
    args = falyx_parsers.parse_args(["init", "test_project"])

    assert args.command == "init"
    assert args.name == "test_project"

    args = falyx_parsers.parse_args(["init-global"])
    assert args.command == "init-global"


def test_run():
    """Test if the run function works correctly."""
    falyx_parsers = get_falyx_parsers()
    args = falyx_parsers.parse_args(["init", "test_project"])
    run(args)
    assert args.command == "init"
    assert args.name == "test_project"
    # Check if the project directory was created
    assert Path("test_project").exists()
    # Clean up
    (Path("test_project") / "falyx.yaml").unlink()
    (Path("test_project") / "tasks.py").unlink()
    Path("test_project").rmdir()
    # Test init-global
    args = falyx_parsers.parse_args(["init-global"])
    run(args)
    # Check if the global config directory was created
    assert (Path.home() / ".config" / "falyx" / "falyx.yaml").exists()
    # Clean up
    (Path.home() / ".config" / "falyx" / "falyx.yaml").unlink()
    (Path.home() / ".config" / "falyx" / "tasks.py").unlink()
    (Path.home() / ".config" / "falyx").rmdir()


def test_no_bootstrap():
    """Test if the main function works correctly when no config file is found."""
    falyx_parsers = get_falyx_parsers()
    args = falyx_parsers.parse_args(["list"])
    assert run(args) is None
    # Check if the task was run
    assert args.command == "list"


def test_run_test_project():
    """Test if the main function works correctly with a test project."""
    falyx_parsers = get_falyx_parsers()
    args = falyx_parsers.parse_args(["init", "test_project"])
    run(args)

    args = falyx_parsers.parse_args(["run", "B"])
    os.chdir("test_project")
    with pytest.raises(SystemExit):
        assert run(args) == "Build complete!"
    os.chdir("..")
    shutil.rmtree("test_project")
    assert not Path("test_project").exists()
