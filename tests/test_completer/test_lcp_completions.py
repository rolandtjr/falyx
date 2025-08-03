from types import SimpleNamespace

import pytest
from prompt_toolkit.document import Document

from falyx.completer import FalyxCompleter


@pytest.fixture
def fake_falyx():
    fake_arg_parser = SimpleNamespace(
        suggest_next=lambda tokens, end: ["AETHERWARP", "AETHERZOOM"]
    )
    fake_command = SimpleNamespace(key="R", aliases=["RUN"], arg_parser=fake_arg_parser)
    return SimpleNamespace(
        exit_command=SimpleNamespace(key="X", aliases=["EXIT"]),
        help_command=SimpleNamespace(key="H", aliases=["HELP"]),
        history_command=SimpleNamespace(key="Y", aliases=["HISTORY"]),
        commands={"R": fake_command},
        _name_map={"R": fake_command, "RUN": fake_command, "X": fake_command},
    )


def test_lcp_completions(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    doc = Document("R A")
    results = list(completer.get_completions(doc, None))
    assert any(c.text == "AETHER" for c in results)
    assert any(c.text == "AETHERWARP" for c in results)
    assert any(c.text == "AETHERZOOM" for c in results)


def test_lcp_completions_space(fake_falyx):
    completer = FalyxCompleter(fake_falyx)
    suggestions = ["London", "New York", "San Francisco"]
    stub = "N"
    completions = list(completer._yield_lcp_completions(suggestions, stub))
    assert any(c.text == '"New York"' for c in completions)
