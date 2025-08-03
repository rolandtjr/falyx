from types import SimpleNamespace

import pytest
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document

from falyx.completer import FalyxCompleter


@pytest.fixture
def fake_falyx():
    fake_arg_parser = SimpleNamespace(
        suggest_next=lambda tokens, end: ["--tag", "--name", "value with space"]
    )
    fake_command = SimpleNamespace(key="R", aliases=["RUN"], arg_parser=fake_arg_parser)
    return SimpleNamespace(
        exit_command=SimpleNamespace(key="X", aliases=["EXIT"]),
        help_command=SimpleNamespace(key="H", aliases=["HELP"]),
        history_command=SimpleNamespace(key="Y", aliases=["HISTORY"]),
        commands={"R": fake_command},
        _name_map={"R": fake_command, "RUN": fake_command, "X": fake_command},
    )


def test_suggest_commands(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    completions = list(completer._suggest_commands("R"))
    assert any(c.text == "R" for c in completions)
    assert any(c.text == "RUN" for c in completions)


def test_suggest_commands_empty(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    completions = list(completer._suggest_commands(""))
    assert any(c.text == "X" for c in completions)
    assert any(c.text == "H" for c in completions)


def test_suggest_commands_no_match(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    completions = list(completer._suggest_commands("Z"))
    assert not completions


def test_get_completions_no_input(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    doc = Document("")
    results = list(completer.get_completions(doc, None))
    assert any(isinstance(c, Completion) for c in results)
    assert any(c.text == "X" for c in results)


def test_get_completions_no_match(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    doc = Document("Z")
    completions = list(completer.get_completions(doc, None))
    assert not completions
    doc = Document("Z Z")
    completions = list(completer.get_completions(doc, None))
    assert not completions


def test_get_completions_partial_command(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    doc = Document("R")
    results = list(completer.get_completions(doc, None))
    assert any(c.text in ("R", "RUN") for c in results)


def test_get_completions_with_flag(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    doc = Document("R ")
    results = list(completer.get_completions(doc, None))
    assert "--tag" in [c.text for c in results]


def test_get_completions_partial_flag(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    doc = Document("R --t")
    results = list(completer.get_completions(doc, None))
    assert all(c.start_position <= 0 for c in results)
    assert any(c.text.startswith("--t") or c.display == "--tag" for c in results)


def test_get_completions_bad_input(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    doc = Document('R "unclosed quote')
    results = list(completer.get_completions(doc, None))
    assert results == []


def test_get_completions_exception_handling(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    fake_falyx.commands["R"].arg_parser.suggest_next = lambda *args: 1 / 0
    doc = Document("R --tag")
    results = list(completer.get_completions(doc, None))
    assert results == []
