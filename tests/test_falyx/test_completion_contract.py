from prompt_toolkit.document import Document

from falyx import Falyx
from falyx.completer import FalyxCompleter
from falyx.parser import CommandArgumentParser


def completion_texts(completions) -> list[str]:
    return [c.text for c in completions]


def make_completion_app() -> tuple[Falyx, FalyxCompleter]:
    flx = Falyx(program="falyx")

    flx.add_option(
        "--profile",
        suggestions=["dev", "prod", "staging"],
        help="Runtime profile",
    )

    flx.add_option(
        "--region",
        choices=["us-east", "us-west"],
        help="Deployment region",
    )

    parser = CommandArgumentParser()
    parser.add_argument("--name")
    parser.add_argument("--env", choices=["dev", "prod"])

    flx.add_command(
        key="D",
        description="Deploy",
        action=lambda name, env: f"deploy {name} to {env}",
        aliases=["deploy"],
        arg_parser=parser,
    )

    return flx, FalyxCompleter(flx)


def test_completion_suggests_namespace_flags():
    _, completer = make_completion_app()

    completions = list(
        completer.get_completions(Document(text="--pr", cursor_position=4), None)
    )

    texts = completion_texts(completions)
    assert "--profile" in texts


def test_completion_suggests_namespace_option_values():
    _, completer = make_completion_app()

    completions = list(
        completer.get_completions(
            Document(text="--profile pr", cursor_position=len("--profile pr")),
            None,
        )
    )

    texts = completion_texts(completions)
    assert "prod" in texts
    assert "dev" not in texts


def test_completion_after_committed_namespace_option_returns_namespace_entries():
    _, completer = make_completion_app()

    completions = list(
        completer.get_completions(
            Document(text="--profile prod de", cursor_position=len("--profile prod de")),
            None,
        )
    )

    texts = completion_texts(completions)
    assert "deploy" in texts


def test_completion_preview_mode_prefixes_namespace_entry_suggestions():
    _, completer = make_completion_app()

    completions = list(
        completer.get_completions(Document(text="?de", cursor_position=3), None)
    )

    texts = completion_texts(completions)
    assert "?deploy" in texts


def test_resolve_completion_route_unresolved_entry_with_trailing_input_stops_namespace_entry_mode():
    flx, _ = make_completion_app()

    route = flx.resolve_completion_route(
        ["wat"],
        stub="--na",
        cursor_at_end_of_token=False,
        invocation_context=flx.get_current_invocation_context(),
        is_preview=False,
    )

    assert route.command is None
    assert route.expecting_entry is False
    assert route.remaining_argv == ["wat", "--na"]
    assert route.stub == ""


def test_completion_delegates_to_command_parser_after_leaf_command_is_resolved():
    _, completer = make_completion_app()

    completions = list(
        completer.get_completions(
            Document(text="D --na", cursor_position=len("D --na")),
            None,
        )
    )

    texts = completion_texts(completions)
    assert "--name" in texts
