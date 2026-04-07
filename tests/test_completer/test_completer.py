import pytest
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document

from falyx import Falyx
from falyx.completer import FalyxCompleter
from falyx.parser import CommandArgumentParser


@pytest.fixture
def falyx():
    flx = Falyx()
    parser = CommandArgumentParser(
        command_key="R",
        command_description="Run Command",
    )
    parser.add_argument(
        "--tag",
    )
    parser.add_argument(
        "--name",
    )
    flx.add_command(
        "R",
        "Run Command",
        lambda x: None,
        aliases=["RUN"],
        arg_parser=parser,
    )
    return flx


def test_suggest_commands(falyx):
    completer = FalyxCompleter(falyx)
    completions = list(completer._suggest_commands("R"))
    assert any(c.text == "R" for c in completions)
    assert any(c.text == "RUN" for c in completions)


def test_suggest_commands_empty(falyx):
    completer = FalyxCompleter(falyx)
    completions = list(completer._suggest_commands(""))
    assert any(c.text == "X" for c in completions)
    assert any(c.text == "H" for c in completions)


def test_suggest_commands_no_match(falyx):
    completer = FalyxCompleter(falyx)
    completions = list(completer._suggest_commands("Z"))
    assert not completions


def test_get_completions_no_input(falyx):
    completer = FalyxCompleter(falyx)
    doc = Document("")
    results = list(completer.get_completions(doc, None))
    assert any(isinstance(c, Completion) for c in results)
    assert any(c.text == "X" for c in results)


def test_get_completions_no_match(falyx):
    completer = FalyxCompleter(falyx)
    doc = Document("Z")
    completions = list(completer.get_completions(doc, None))
    assert not completions
    doc = Document("Z Z")
    completions = list(completer.get_completions(doc, None))
    assert not completions


def test_get_completions_partial_command(falyx):
    completer = FalyxCompleter(falyx)
    doc = Document("R")
    results = list(completer.get_completions(doc, None))
    assert any(c.text in ("R", "RUN") for c in results)


def test_get_completions_with_flag(falyx):
    completer = FalyxCompleter(falyx)
    doc = Document("R ")
    results = list(completer.get_completions(doc, None))
    assert "--tag" in [c.text for c in results]


def test_get_completions_partial_flag(falyx):
    completer = FalyxCompleter(falyx)
    doc = Document("R --t")
    results = list(completer.get_completions(doc, None))
    assert all(c.start_position <= 0 for c in results)
    assert any(c.text.startswith("--t") or c.display == "--tag" for c in results)


def test_get_completions_bad_input(falyx):
    completer = FalyxCompleter(falyx)
    doc = Document('R "unclosed quote')
    results = list(completer.get_completions(doc, None))
    assert results == []


def test_get_completions_exception_handling(falyx):
    completer = FalyxCompleter(falyx)
    falyx.commands["R"].arg_parser.suggest_next = lambda *args: 1 / 0
    doc = Document("R --tag")
    results = list(completer.get_completions(doc, None))
    assert results == []
