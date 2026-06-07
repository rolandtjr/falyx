from types import SimpleNamespace

import pytest

from falyx.completer import FalyxCompleter


def completion_texts(completions) -> list[str]:
    return [c.text for c in completions]


def test_lcp_completions():
    completer = FalyxCompleter(SimpleNamespace())
    suggestions = ["AETHERWARP", "AETHERZOOM"]
    stub = "A"
    completions = list(completer._yield_lcp_completions(suggestions, stub))
    texts = completion_texts(completions)

    assert "AETHER" in texts
    assert "AETHERWARP" in texts
    assert "AETHERZOOM" in texts


def test_lcp_completions_space():
    completer = FalyxCompleter(SimpleNamespace())
    suggestions = ["London", "New York", "San Francisco"]
    stub = "N"
    completions = list(completer._yield_lcp_completions(suggestions, stub))
    texts = completion_texts(completions)
    assert '"New York"' in texts


def test_lcp_completions_does_not_collapse_flags():
    completer = FalyxCompleter(SimpleNamespace())
    suggestions = ["--tag", "--target"]
    stub = "--t"
    completions = list(completer._yield_lcp_completions(suggestions, stub))
    texts = completion_texts(completions)

    assert "--tag" in texts
    assert "--target" in texts
    assert "--ta" not in texts
