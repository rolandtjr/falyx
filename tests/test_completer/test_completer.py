import re

import pytest
from prompt_toolkit.completion import Completion
from prompt_toolkit.document import Document

from falyx import Falyx
from falyx.completer import FalyxCompleter
from falyx.parser import CommandArgumentParser


def completion_texts(completions) -> list[str]:
    return [c.text for c in completions]


@pytest.fixture
def falyx():
    flx = Falyx()

    run_parser = CommandArgumentParser(
        command_key="R",
        command_description="Run Command",
    )
    run_parser.add_argument("--tag")
    run_parser.add_argument("--name")

    flx.add_command(
        "R",
        "Run Command",
        lambda: None,
        aliases=["RUN"],
        arg_parser=run_parser,
    )

    ops = Falyx(program="ops")

    deploy_parser = CommandArgumentParser(
        command_key="D",
        command_description="Deploy Command",
    )
    deploy_parser.add_argument("--target")
    deploy_parser.add_argument("--region")

    ops.add_command(
        "D",
        "Deploy Command",
        lambda: None,
        aliases=["DEPLOY"],
        arg_parser=deploy_parser,
    )

    flx.add_submenu(
        "OPS",
        "Operations",
        ops,
        aliases=["OPERATIONS"],
    )

    return flx


def test_suggest_namespace_entries_root(falyx):
    completer = FalyxCompleter(falyx)

    completions = completer._suggest_namespace_entries(falyx, "R")

    assert "R" in completions
    assert "RUN" in completions

    completions = completer._suggest_namespace_entries(falyx, "r")

    assert "r" in completions
    assert "run" in completions


def test_suggest_namespace_entries_submenu(falyx):
    completer = FalyxCompleter(falyx)
    ops = falyx.namespaces["OPS"].namespace

    completions = completer._suggest_namespace_entries(ops, "D")

    assert "D" in completions
    assert "DEPLOY" in completions


def test_get_completions_no_input_shows_root_entries(falyx):
    completer = FalyxCompleter(falyx)

    results = list(completer.get_completions(Document(""), None))
    texts = completion_texts(results)

    assert any(isinstance(c, Completion) for c in results)
    assert "R" in texts
    assert "OPS" in texts
    assert "X" in texts


def test_get_completions_partial_root_entry(falyx):
    completer = FalyxCompleter(falyx)

    results = list(completer.get_completions(Document("OP"), None))
    texts = completion_texts(results)

    assert "OPS" in texts
    assert "OPERATIONS" in texts


def test_get_completions_no_match_returns_empty(falyx):
    completer = FalyxCompleter(falyx)

    assert list(completer.get_completions(Document("Z"), None)) == []
    assert list(completer.get_completions(Document("OPS Z"), None)) == []


def test_get_completions_namespace_boundary_suggests_help_flags(falyx):
    completer = FalyxCompleter(falyx)

    results = list(completer.get_completions(Document("OPS -"), None))
    texts = completion_texts(results)

    assert "-h" in texts
    assert "--help" in texts
    assert "-T" in texts
    assert "--tldr" in texts


def test_get_completions_preview_prefix_is_preserved(falyx):
    completer = FalyxCompleter(falyx)

    results = list(completer.get_completions(Document("?R"), None))
    texts = completion_texts(results)

    assert any(text.startswith("?R") for text in texts)


def test_get_completions_preview_prefix_for_namespace_entries(falyx):
    completer = FalyxCompleter(falyx)

    results = list(completer.get_completions(Document("?OP"), None))
    texts = completion_texts(results)

    assert "?OPS" in texts or "?OPERATIONS" in texts


def test_get_completions_leaf_command_delegates_flags_to_root_command_parser(
    falyx, monkeypatch
):
    completer = FalyxCompleter(falyx)

    seen = {}

    def fake_suggest_next(args, cursor_at_end_of_token):
        seen["args"] = list(args)
        seen["cursor_at_end_of_token"] = cursor_at_end_of_token
        return ["--tag"]

    monkeypatch.setattr(
        falyx.commands["R"].arg_parser,
        "suggest_next",
        fake_suggest_next,
    )

    results = list(completer.get_completions(Document("R --t"), None))
    texts = completion_texts(results)

    assert seen["args"] == ["--t"]
    assert seen["cursor_at_end_of_token"] is False
    assert "--tag" in texts


def test_get_completions_leaf_command_delegates_flags_to_submenu_command_parser(
    falyx, monkeypatch
):
    completer = FalyxCompleter(falyx)
    ops = falyx.namespaces["OPS"].namespace
    deploy = ops.commands["D"]

    seen = {}

    def fake_suggest_next(args, cursor_at_end_of_token):
        seen["args"] = list(args)
        seen["cursor_at_end_of_token"] = cursor_at_end_of_token
        return ["--target"]

    monkeypatch.setattr(
        deploy.arg_parser,
        "suggest_next",
        fake_suggest_next,
    )

    results = list(completer.get_completions(Document("OPS D --t"), None))
    texts = completion_texts(results)

    assert seen["args"] == ["--t"]
    assert seen["cursor_at_end_of_token"] is False
    assert "--target" in texts


def test_get_completions_leaf_command_receives_empty_stub_after_space(falyx, monkeypatch):
    completer = FalyxCompleter(falyx)

    seen = {}

    def fake_suggest_next(args, cursor_at_end_of_token):
        seen["args"] = list(args)
        seen["cursor_at_end_of_token"] = cursor_at_end_of_token
        return ["--tag", "--name"]

    monkeypatch.setattr(
        falyx.commands["R"].arg_parser,
        "suggest_next",
        fake_suggest_next,
    )

    results = list(completer.get_completions(Document("R "), None))
    texts = completion_texts(results)

    assert seen["args"] == []
    assert seen["cursor_at_end_of_token"] is True
    assert "--tag" in texts
    assert "--name" in texts


def test_get_completions_bad_input(falyx):
    completer = FalyxCompleter(falyx)

    results = list(completer.get_completions(Document('R "unclosed quote'), None))

    assert results == []


def test_get_completions_exception_handling(falyx, monkeypatch):
    completer = FalyxCompleter(falyx)

    def boom(*args, **kwargs):
        raise ZeroDivisionError("boom")

    monkeypatch.setattr(falyx.commands["R"].arg_parser, "suggest_next", boom)

    results = list(completer.get_completions(Document("R --tag"), None))

    assert results == []


def test_ensure_quote_wraps_whitespace(falyx):
    completer = FalyxCompleter(falyx)

    assert completer._ensure_quote("hello world") == '"hello world"'
    assert completer._ensure_quote("hello") == "hello"
