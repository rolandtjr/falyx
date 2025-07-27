import shutil
import sys
import tempfile
from argparse import ArgumentParser, Namespace, _SubParsersAction
from pathlib import Path

import pytest

from falyx.__main__ import (
    bootstrap,
    find_falyx_config,
    get_parsers,
    init_callback,
    init_config,
    main,
)
from falyx.parser import CommandArgumentParser


@pytest.fixture(autouse=True)
def fake_home(monkeypatch):
    """Redirect Path.home() to a temporary directory for all tests."""
    temp_home = Path(tempfile.mkdtemp())
    monkeypatch.setattr(Path, "home", lambda: temp_home)
    yield temp_home
    shutil.rmtree(temp_home, ignore_errors=True)


@pytest.fixture(autouse=True)
def setup_teardown():
    """Fixture to set up and tear down the environment for each test."""
    cwd = Path.cwd()
    yield
    for file in cwd.glob("falyx.yaml"):
        file.unlink(missing_ok=True)
    for file in cwd.glob("falyx.toml"):
        file.unlink(missing_ok=True)


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


@pytest.mark.asyncio
async def test_init_config():
    """Test if the init_config function adds the correct argument."""
    parser = CommandArgumentParser()
    init_config(parser)
    args = await parser.parse_args(["test_project"])
    assert args["name"] == "test_project"

    # Test with default value
    args = await parser.parse_args([])
    assert args["name"] == "."


def test_init_callback(tmp_path):
    """Test if the init_callback function works correctly."""
    # Test project initialization
    args = Namespace(command="init", name=str(tmp_path))
    init_callback(args)
    assert (tmp_path / "falyx.yaml").exists()


def test_init_global_callback():
    # Test global initialization
    args = Namespace(command="init_global")
    init_callback(args)
    assert (Path.home() / ".config" / "falyx" / "tasks.py").exists()
    assert (Path.home() / ".config" / "falyx" / "falyx.yaml").exists()


def test_get_parsers():
    """Test if the get_parsers function returns the correct parsers."""
    root_parser, subparsers = get_parsers()
    assert isinstance(root_parser, ArgumentParser)
    assert isinstance(subparsers, _SubParsersAction)

    # Check if the 'init' command is available
    init_parser = subparsers.choices.get("init")
    assert init_parser is not None
    assert "name" == init_parser._get_positional_actions()[0].dest


def test_main():
    """Test if the main function runs with the correct arguments."""

    sys.argv = ["falyx", "run", "?"]

    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0
