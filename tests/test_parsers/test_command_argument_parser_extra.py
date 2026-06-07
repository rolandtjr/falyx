from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from falyx.action.action import Action
from falyx.exceptions import CommandArgumentError, InvalidValueError
from falyx.execution_option import ExecutionOption
from falyx.parser.command_argument_parser import CommandArgumentParser
from falyx.signals import HelpSignal


@pytest.fixture
def parser() -> CommandArgumentParser:
    return CommandArgumentParser(
        command_key="D",
        command_description="Deploy service",
        help_text="Deploy a service.",
        help_epilog="Deployment epilog.",
        aliases=["deploy"],
        program="flx",
    )


def capture_console(parser: CommandArgumentParser) -> StringIO:
    stream = StringIO()
    parser.console = Console(
        file=stream,
        force_terminal=False,
        color_system=None,
        width=120,
    )
    return stream


def test_add_argument_rejects_suggestions_with_non_string_members(
    parser: CommandArgumentParser,
) -> None:
    with pytest.raises(
        CommandArgumentError, match="suggestions must be a list of strings"
    ):
        parser.add_argument("--region", suggestions=["dev", 1])


@pytest.mark.asyncio
async def test_parse_accepts_multi_value_choice_list_when_all_values_are_valid(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument(
        "--ports",
        type=int,
        nargs="+",
        choices=["80", 443],
        default=[],
    )

    result = await parser.parse_args(["--ports", "80", "443"])

    assert result["ports"] == [80, 443]


@pytest.mark.asyncio
async def test_positional_action_wraps_resolver_failure(
    parser: CommandArgumentParser,
) -> None:
    async def fail_resolver(value: str) -> str:
        raise RuntimeError(f"cannot resolve {value}")

    parser.add_argument(
        "target",
        action="action",
        resolver=Action("Resolve target", fail_resolver),
        lazy_resolver=False,
    )

    with pytest.raises(
        CommandArgumentError, match=r"\[target\] action failed: cannot resolve web"
    ):
        await parser.parse_args(["web"])


@pytest.mark.asyncio
async def test_dash_prefixed_numeric_token_can_be_a_positional_value(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("delta", type=int)

    result = await parser.parse_args(["-3"])

    assert result["delta"] == -3


@pytest.mark.asyncio
async def test_store_option_without_value_raises_type_specific_prompt(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("--count", type=int, help="Number of instances.")

    with pytest.raises(CommandArgumentError, match="enter a int value for 'count'"):
        await parser.parse_args(["--count"])


@pytest.mark.asyncio
async def test_append_option_without_value_raises_type_specific_prompt(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("--tag", action="append", help="Deployment tag.")

    with pytest.raises(CommandArgumentError, match="enter a str value for 'tag'"):
        await parser.parse_args(["--tag"])


@pytest.mark.asyncio
async def test_tldr_flag_on_help_command_is_parsed_as_a_normal_value(
    parser: CommandArgumentParser,
) -> None:
    parser.mark_as_help_command()
    parser.add_tldr_example("D --region us-east", "Deploy to us-east")

    result = await parser.parse_args(["--tldr"])

    assert result["tldr"] is True


@pytest.mark.asyncio
async def test_tldr_flag_renders_examples_and_raises_help_signal(
    parser: CommandArgumentParser,
) -> None:
    stream = capture_console(parser)
    parser.add_tldr_example("--region us-east", "Deploy to us-east")

    with pytest.raises(HelpSignal):
        await parser.parse_args(["--tldr"])

    output = stream.getvalue()
    assert "usage:" in output
    assert "examples:" in output
    assert "Deploy to us-east" in output
    assert "--region us-east" in output


@pytest.mark.asyncio
async def test_required_mutex_group_requires_one_member(
    parser: CommandArgumentParser,
) -> None:
    mode = parser.add_mutually_exclusive_group("mode", required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")

    with pytest.raises(
        CommandArgumentError, match="one of the following is required for group 'mode'"
    ):
        await parser.parse_args([])


@pytest.mark.asyncio
async def test_mutex_group_rejects_multiple_present_members(
    parser: CommandArgumentParser,
) -> None:
    mode = parser.add_mutually_exclusive_group("mode")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")

    with pytest.raises(
        CommandArgumentError,
        match="cannot be used together: (dry_run, apply|apply, dry_run)",
    ):
        await parser.parse_args(["--dry-run", "--apply"])


@pytest.mark.parametrize(
    ("argument_kwargs", "argv"),
    [
        ({"flags": ("--enabled",), "action": "store_true"}, ["--enabled", "--other"]),
        ({"flags": ("--disabled",), "action": "store_false"}, ["--disabled", "--other"]),
        (
            {"flags": ("--feature",), "action": "store_bool_optional"},
            ["--no-feature", "--other"],
        ),
        ({"flags": ("-v", "--verbose"), "action": "count"}, ["-v", "--other"]),
        ({"flags": ("--tag",), "action": "append"}, ["--tag", "beta", "--other"]),
        (
            {"flags": ("--item",), "action": "extend", "nargs": "+"},
            ["--item", "a", "--other"],
        ),
        ({"flags": ("--name",)}, ["--name", "web", "--other"]),
    ],
)
@pytest.mark.asyncio
async def test_mutex_presence_detection_handles_all_supported_action_shapes(
    argument_kwargs: dict,
    argv: list[str],
) -> None:
    parser = CommandArgumentParser(command_key="D")
    only_one = parser.add_mutually_exclusive_group("only-one")
    kwargs = argument_kwargs.copy()
    flags = kwargs.pop("flags")
    only_one.add_argument(*flags, **kwargs)
    only_one.add_argument("--other", action="store_true")

    with pytest.raises(CommandArgumentError, match="cannot be used together"):
        await parser.parse_args(argv)


@pytest.mark.asyncio
async def test_parse_args_split_separates_execution_options_from_command_inputs(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("service")
    parser.add_argument("--region", default="us-east")
    parser.enable_execution_options(
        frozenset(
            {
                ExecutionOption.SUMMARY,
                ExecutionOption.RETRY,
                ExecutionOption.CONFIRM,
            }
        )
    )

    args, kwargs, execution_args = await parser.parse_args_split(
        [
            "api",
            "--region",
            "us-west",
            "--summary",
            "--retries",
            "3",
            "--retry-delay",
            "0.5",
            "--retry-backoff",
            "2.0",
            "--skip-confirm",
        ]
    )

    assert args == ("api",)
    assert kwargs == {"region": "us-west"}
    assert execution_args == {
        "summary": True,
        "retries": 3,
        "retry_delay": 0.5,
        "retry_backoff": 2.0,
        "force_confirm": False,
        "skip_confirm": True,
    }


@pytest.mark.asyncio
async def test_lazy_action_required_argument_is_deferred_during_validation(
    parser: CommandArgumentParser,
) -> None:
    calls: list[str] = []

    async def resolve(value: str) -> str:
        calls.append(value)
        return value.upper()

    parser.add_argument(
        "--target",
        action="action",
        resolver=Action("Resolve target", resolve),
        required=True,
    )

    result = await parser.parse_args(["--target", "web"], from_validate=True)

    assert result["target"] is None
    assert calls == []


@pytest.mark.asyncio
async def test_lazy_action_required_argument_still_errors_when_no_tokens_are_present(
    parser: CommandArgumentParser,
) -> None:
    async def resolve(value: str) -> str:
        return value.upper()

    parser.add_argument(
        "--target",
        action="action",
        resolver=Action("Resolve target", resolve),
        required=True,
    )

    with pytest.raises(CommandArgumentError, match="missing required argument 'target'"):
        await parser.parse_args([], from_validate=True)


@pytest.mark.asyncio
async def test_default_list_with_wrong_fixed_nargs_arity_is_invalid(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("--pair", nargs=2, default=["only-one"])

    with pytest.raises(InvalidValueError) as exc_info:
        await parser.parse_args([])

    assert exc_info.value.dest == "pair"
    assert "expected 2" in str(exc_info.value)


@pytest.mark.asyncio
async def test_required_plus_nargs_option_requires_at_least_one_value(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("--item", nargs="+", required=True)

    with pytest.raises(
        CommandArgumentError, match="argument 'item' requires at least one value"
    ):
        await parser.parse_args([])


@pytest.mark.asyncio
async def test_suggest_next_filters_mutex_siblings_after_one_member_is_consumed(
    parser: CommandArgumentParser,
) -> None:
    mode = parser.add_mutually_exclusive_group("mode")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--region", choices=["us-east", "us-west"])

    await parser.parse_args(["--dry-run"])

    suggestions = parser.suggest_next(["--dry-run"], cursor_at_end_of_token=True)

    assert "--apply" not in suggestions
    assert "--region" in suggestions


@pytest.mark.asyncio
async def test_optional_choice_argument_can_be_omitted(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--region", choices=["us-east", "us-west"])

    result = await parser.parse_args(["--dry-run"])

    assert result["dry_run"] is True
    assert result["region"] is None


@pytest.mark.asyncio
async def test_suggest_next_returns_no_values_after_invalid_choice_is_committed(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("--region", choices=["dev", "prod"])

    with pytest.raises(InvalidValueError):
        await parser.parse_args(["--region", "qa"])

    assert parser.suggest_next(["--region", "qa"], cursor_at_end_of_token=True) == []


@pytest.mark.asyncio
async def test_suggest_next_suggests_value_for_keyword_when_stub_starts_with_dash(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("--profile", suggestions=["-prod", "-stage", "dev"])

    with pytest.raises(CommandArgumentError):
        await parser.parse_args(["--profile"], from_validate=True)

    assert parser.suggest_next(["--profile", "-"], cursor_at_end_of_token=False) == [
        "-prod",
        "-stage",
    ]


@pytest.mark.asyncio
async def test_suggest_next_returns_empty_for_missing_path_base(
    parser: CommandArgumentParser,
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing-dir" / "config.toml"
    parser.add_argument("--config", type=Path)

    await parser.parse_args(["--config", str(missing)], from_validate=True)

    assert (
        parser.suggest_next(["--config", str(missing)], cursor_at_end_of_token=False)
        == []
    )


def test_get_options_text_repeats_fixed_width_positional_nargs(
    parser: CommandArgumentParser,
) -> None:
    parser.add_argument("coords", nargs=2)

    assert "coords coords" in parser.get_options_text()


def test_get_usage_uses_program_only_when_parser_is_in_runner_mode(
    parser: CommandArgumentParser,
) -> None:
    parser.is_runner_mode = True
    parser.program = "deploy-tool"

    usage = parser.get_usage()

    assert "deploy-tool" in usage
    assert "[bold]D[/bold]" not in usage
    assert "[bold]deploy[/bold]" not in usage


def test_render_help_includes_grouped_keywords_bool_optional_pair_and_epilog(
    parser: CommandArgumentParser,
) -> None:
    stream = capture_console(parser)
    parser.add_argument("environment", help="Target environment.")
    deploy = parser.add_argument_group("deploy", "Deployment options.")
    deploy.add_argument("--region", help="Target region.")
    mode = parser.add_mutually_exclusive_group("mode")
    mode.add_argument("--dry-run", action="store_true", help="Preview only.")
    parser.add_argument("--cache", action="store_bool_optional", help="Use cache.")

    parser.render_help()

    output = stream.getvalue()
    assert "usage:" in output
    assert "Deploy a service." in output
    assert "positional:" in output
    assert "environment" in output
    assert "deploy:" in output
    assert "Deployment options." in output
    assert "--cache, --no-cache" in output
    assert "Deployment epilog." in output


def test_render_tldr_without_examples_prints_empty_state_message(
    parser: CommandArgumentParser,
) -> None:
    stream = capture_console(parser)

    parser.render_tldr()

    assert "No TLDR examples available for D" in stream.getvalue()


def test_render_tldr_with_examples_prints_usage_help_and_example_panel(
    parser: CommandArgumentParser,
) -> None:
    stream = capture_console(parser)
    parser.add_tldr_example("--region us-east", "Deploy east")

    parser.render_tldr()

    output = stream.getvalue()
    assert "usage:" in output
    assert "Deploy a service." in output
    assert "examples:" in output
    assert "Deploy east" in output
    assert "--region us-east" in output
