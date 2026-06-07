from __future__ import annotations

import pytest

from falyx import Falyx
from falyx.exceptions import EntryNotFoundError, FalyxOptionError
from falyx.mode import FalyxMode
from falyx.parser.falyx_parser import FalyxParser
from falyx.parser.option import Option
from falyx.parser.parser_types import FalyxTLDRExample


@pytest.fixture
def flx() -> Falyx:
    flx = Falyx()
    flx.add_command(
        "D",
        description="Deploy command",
        action=lambda: "deploy",
        aliases=["deploy"],
    )
    return flx


@pytest.fixture
def parser(flx: Falyx) -> FalyxParser:
    return FalyxParser(flx)


def test_init_registers_reserved_options_by_default(parser: FalyxParser) -> None:
    flags = parser.get_flags()

    assert "-h" in flags
    assert "-v" in flags
    assert "-d" in flags
    assert "-n" in flags
    assert parser.help_option is not None
    assert parser.tldr_option is None


def test_init_respects_disabled_reserved_root_options() -> None:
    parser = FalyxParser(
        Falyx(
            disable_verbose_option=True,
            disable_debug_hooks_option=True,
            disable_never_prompt_option=True,
        )
    )

    assert parser.get_flags() == ["-h"]

    with pytest.raises(FalyxOptionError, match="unknown option '-v'"):
        parser.parse_args(["-v"])


def test_get_options_returns_registered_options(parser: FalyxParser) -> None:
    parser.add_option("--region", "-r", default="us-east")

    options = parser.get_options()

    assert any(option.dest == "region" for option in options)
    assert parser.get_flags()[-1] == "--region"


def test_add_option_registers_store_option_with_default_and_choices(
    parser: FalyxParser,
) -> None:
    parser.add_option(
        "--region",
        "-r",
        default="us-east",
        choices=["us-east", "us-west"],
    )

    result = parser.parse_args(["--region", "us-west", "deploy"])

    assert result.namespace_options["region"] == "us-west"
    assert result.namespace_defaults["region"] == "us-east"
    assert result.remaining_argv == ["deploy"]


def test_add_option_infers_dest_from_long_flag(parser: FalyxParser) -> None:
    parser.add_option("--dry-run-mode", default="safe")

    result = parser.parse_args([])

    assert result.namespace_defaults["dry_run_mode"] == "safe"


def test_add_option_uses_explicit_dest(parser: FalyxParser) -> None:
    parser.add_option("--profile-name", dest="profile", default="dev")

    result = parser.parse_args(["--profile-name", "prod"])

    assert result.namespace_options["profile"] == "prod"


@pytest.mark.parametrize(
    ("flags", "match"),
    [
        ((), "no flags provided"),
        (("region",), "must start with '-'"),
        (("--",), "long flags must have at least one character"),
        (("-abc",), "short flags must be a single character"),
    ],
)
def test_add_option_rejects_invalid_flags(
    parser: FalyxParser,
    flags: tuple[str, ...],
    match: str,
) -> None:
    with pytest.raises(FalyxOptionError, match=match):
        parser.add_option(*flags)


@pytest.mark.parametrize("dest", ["help", "tldr"])
def test_add_option_rejects_reserved_dests(
    parser: FalyxParser,
    dest: str,
) -> None:
    with pytest.raises(FalyxOptionError, match="reserved"):
        parser.add_option("--custom", dest=dest)


def test_add_option_rejects_duplicate_dest(parser: FalyxParser) -> None:
    parser.add_option("--region")

    with pytest.raises(FalyxOptionError, match="duplicate option dest 'region'"):
        parser.add_option("--region-name", dest="region")


def test_add_option_rejects_duplicate_flag(parser: FalyxParser) -> None:
    parser.add_option("--region")

    with pytest.raises(FalyxOptionError, match="already used"):
        parser.add_option("--region", dest="other_region")


@pytest.mark.parametrize(
    ("dest", "match"),
    [
        ("bad-dest", "valid identifier"),
        ("1bad", "cannot start with a digit"),
    ],
)
def test_add_option_rejects_invalid_explicit_dest(
    parser: FalyxParser,
    dest: str,
    match: str,
) -> None:
    with pytest.raises(FalyxOptionError, match=match):
        parser.add_option("--valid", dest=dest)


def test_add_option_rejects_invalid_action(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="invalid option action"):
        parser.add_option("--region", action="not-real")


def test_add_option_rejects_invalid_store_true_default(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="must be False or None"):
        parser.add_option("--foo", action="store_true", default=True)


def test_add_option_rejects_invalid_store_false_default(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="must be True or None"):
        parser.add_option("--foo", action="store_false", default=False)


def test_add_option_rejects_invalid_store_bool_optional_default(
    parser: FalyxParser,
) -> None:
    with pytest.raises(
        FalyxOptionError,
        match="default value for 'store_bool_optional' action must be None",
    ):
        parser.add_option("--foo", action="store_bool_optional", default="not-bool")


def test_add_option_rejects_default_for_help_or_tldr_option(parser: FalyxParser) -> None:
    with pytest.raises(
        FalyxOptionError, match="default value cannot be set for action 'help'"
    ):
        parser.add_option("--additional-help", action="help", default=True)

    with pytest.raises(
        FalyxOptionError, match="default value cannot be set for action 'tldr'"
    ):
        parser.add_option("--more-tldr", action="tldr", default=True)


def test_add_option_rejects_choices_for_boolean_option(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="choices cannot be specified"):
        parser.add_option("--foo", action="store_true", choices=["yes"])


def test_add_option_rejects_default_outside_choices(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="not in allowed choices"):
        parser.add_option(
            "--region",
            default="eu-central",
            choices=["us-east", "us-west"],
        )


def test_add_option_rejects_invalid_default_type(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="cannot be coerced to int"):
        parser.add_option("--retries", type=int, default="not-an-int")


def test_add_option_rejects_invalid_choice_type(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="invalid choice"):
        parser.add_option("--retries", type=int, choices=["1", "bad"])


def test_add_option_rejects_non_list_suggestions(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="suggestions must be a list or None"):
        parser.add_option("--profile", suggestions=("dev", "prod"))


def test_add_option_rejects_non_string_suggestions(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="suggestions must be a list of strings"):
        parser.add_option("--profile", suggestions=["dev", 1])


def test_add_option_rejects_non_string_flags(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="invalid flag '123': must be a string"):
        parser.add_option("--region", 123)


def test_add_option_rejects_flags_with_invalid_prefix(parser: FalyxParser) -> None:
    with pytest.raises(
        FalyxOptionError, match="invalid flag 'region': must start with '-'"
    ):
        parser.add_option("region")


def test_add_option_rejects_long_flag_with_insufficient_length(
    parser: FalyxParser,
) -> None:
    with pytest.raises(
        FalyxOptionError, match="long flags must have at least one character after '--'"
    ):
        parser.add_option("--", dest="invalid")


def test_add_option_rejects_speacial_characters_in_dest(parser: FalyxParser) -> None:
    with pytest.raises(
        FalyxOptionError, match="invalid dest 'bad-dest': must be a valid identifier"
    ):
        parser.add_option("--bad-dest", dest="bad-dest")

    with pytest.raises(
        FalyxOptionError, match=r"invalid dest 'bad\*dest': must be a valid identifier"
    ):
        parser.add_option("--bad-dest", dest="bad*dest")

    with pytest.raises(
        FalyxOptionError, match="invalid dest '1bad-dest': must be a valid identifier"
    ):
        parser.add_option("--bad-dest", dest="1bad-dest")


def test_add_option_rejects_dest_starting_with_digit(parser: FalyxParser) -> None:
    with pytest.raises(
        FalyxOptionError, match="invalid dest '1bad': cannot start with a digit"
    ):
        parser.add_option("--1bad", dest="1bad")


def test_add_option_rejects_special_characters_in_flags(parser: FalyxParser) -> None:
    with pytest.raises(
        FalyxOptionError,
        match=r"invalid flag '--bad\*flag': must only contain letters, digits, underscores, or hyphens",
    ):
        parser.add_option("--bad*flag", dest="bad_flag")


def test_add_option_rejects_short_flag_with_multiple_characters(
    parser: FalyxParser,
) -> None:
    with pytest.raises(
        FalyxOptionError,
        match="invalid flag '-ab': short flags must be a single character",
    ):
        parser.add_option("-ab")


def test_add_option_rejects_bad_flags(parser: FalyxParser) -> None:
    with pytest.raises(
        FalyxOptionError,
        match="--region1@': must only contain letters, digits, underscores, or hyphens",
    ):
        parser.add_option("--region1@")

    with pytest.raises(
        FalyxOptionError, match="invalid dest '42region': cannot start with a digit"
    ):
        parser.add_option("--42region")


def test_register_option_rejects_duplicate_flag(parser: FalyxParser) -> None:
    parser.add_option("--region", "-r")
    parser.add_option("--profile", "-p")

    option1 = Option(flags=("--region", "-r"), dest="region")
    option2 = Option(flags=("--profile", "-p"), dest="profile")

    with pytest.raises(FalyxOptionError, match="already used"):
        parser._register_option(option1)

    with pytest.raises(FalyxOptionError, match="already used"):
        parser._register_option(option2)


def test_parse_args_with_no_args_returns_defaults(parser: FalyxParser) -> None:
    result = parser.parse_args([])

    assert result.mode is FalyxMode.COMMAND
    assert result.raw_argv == []
    assert result.remaining_argv == []
    assert result.current_head == ""
    assert result.help is False
    assert result.tldr is False
    assert result.namespace_defaults["help"] is False
    assert result.root_defaults["verbose"] is False
    assert result.root_defaults["debug_hooks"] is False
    assert result.root_defaults["never_prompt"] is False


def test_parse_args_splits_root_and_namespace_options(parser: FalyxParser) -> None:
    parser.add_option("--profile", default="dev")

    result = parser.parse_args(["--verbose", "--profile", "prod", "deploy"])

    assert result.root_options == {"verbose": True}
    assert result.namespace_options == {"profile": "prod"}
    assert result.remaining_argv == ["deploy"]
    assert result.current_head == "deploy"


@pytest.mark.parametrize("help_flag", ["-h", "--help"])
def test_parse_args_help_flag_sets_help_mode(
    parser: FalyxParser,
    help_flag: str,
) -> None:
    result = parser.parse_args([help_flag])

    assert result.mode is FalyxMode.HELP
    assert result.help is True
    assert result.namespace_options["help"] is True
    assert result.remaining_argv == []


def test_parse_args_tldr_flag_sets_help_mode_after_tldr_registered(
    parser: FalyxParser,
) -> None:
    parser.add_tldr_example(
        entry_key="D",
        usage="--region us-east",
        description="Deploy to us-east",
    )

    result = parser.parse_args(["--tldr"])

    assert result.mode is FalyxMode.HELP
    assert result.tldr is True
    assert result.namespace_options["tldr"] is True


def test_parse_args_unknown_leading_option_raises(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="unknown option '--wat'"):
        parser.parse_args(["--wat"])


def test_parse_args_stops_at_first_non_option_boundary(parser: FalyxParser) -> None:
    result = parser.parse_args(["deploy", "--verbose", "--never-prompt"])

    assert result.root_options == {}
    assert result.namespace_options == {}
    assert result.remaining_argv == ["deploy", "--verbose", "--never-prompt"]
    assert result.current_head == "deploy"


def test_parse_args_allows_unknown_options_after_route_boundary(
    parser: FalyxParser,
) -> None:
    result = parser.parse_args(["deploy", "--command-local-option"])

    assert result.remaining_argv == ["deploy", "--command-local-option"]


def test_parse_args_store_true_and_store_false(parser: FalyxParser) -> None:
    parser.add_option("--json", action="store_true")
    parser.add_option("--color", action="store_false")

    result = parser.parse_args(["--json", "--color"])

    assert result.namespace_defaults["json"] is False
    assert result.namespace_defaults["color"] is True
    assert result.namespace_options["json"] is True
    assert result.namespace_options["color"] is False


def test_parse_args_count_option(parser: FalyxParser) -> None:
    parser.add_option("-q", "--quiet", action="count")

    result = parser.parse_args(["-q", "-q", "--quiet"])

    assert result.namespace_defaults["quiet"] == 0
    assert result.namespace_options["quiet"] == 3


def test_parse_args_posix_bundles_boolean_and_count_options(
    parser: FalyxParser,
) -> None:
    parser.add_option("-q", "--quiet", action="count")

    result = parser.parse_args(["-vdnq", "deploy"])

    assert result.root_options == {
        "verbose": True,
        "debug_hooks": True,
        "never_prompt": True,
    }
    assert result.namespace_options == {"quiet": 1}
    assert result.remaining_argv == ["deploy"]


def test_parse_args_posix_bundle_can_end_with_store_option(
    parser: FalyxParser,
) -> None:
    parser.add_option("-q", "--quiet", action="count")
    parser.add_option("-r", "--region")

    result = parser.parse_args(["-qr", "us-east", "deploy"])

    assert result.namespace_options == {
        "quiet": 1,
        "region": "us-east",
    }
    assert result.remaining_argv == ["deploy"]


def test_parse_args_does_not_expand_invalid_posix_bundle(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="unknown option '-vz'"):
        parser.parse_args(["-vz"])


def test_parse_args_store_option_requires_value(parser: FalyxParser) -> None:
    parser.add_option("--region")

    with pytest.raises(FalyxOptionError, match="expected a value"):
        parser.parse_args(["--region"])


def test_parse_args_store_option_coerces_value(parser: FalyxParser) -> None:
    parser.add_option("--retries", type=int)

    result = parser.parse_args(["--retries", "3"])

    assert result.namespace_options["retries"] == 3


def test_parse_args_store_option_rejects_invalid_value(parser: FalyxParser) -> None:
    parser.add_option("--retries", type=int)

    with pytest.raises(FalyxOptionError, match="invalid value for '--retries'"):
        parser.parse_args(["--retries", "abc"])


def test_parse_args_store_option_rejects_value_outside_choices(
    parser: FalyxParser,
) -> None:
    parser.add_option("--region", choices=["us-east", "us-west"])

    with pytest.raises(FalyxOptionError, match="expected one of"):
        parser.parse_args(["--region", "eu-central"])


def test_suggest_next_returns_no_suggestions_for_empty_args(
    parser: FalyxParser,
) -> None:
    suggestions, expecting_value = parser.suggest_next([], cursor_at_end_of_token=False)

    assert suggestions == []
    assert expecting_value is False


def test_suggest_next_suggests_matching_option_flags(parser: FalyxParser) -> None:
    parser.add_option("--region", "-r")

    suggestions, expecting_value = parser.suggest_next(
        ["--r"],
        cursor_at_end_of_token=False,
    )

    assert suggestions == ["--region"]
    assert expecting_value is False


def test_suggest_next_suggests_all_remaining_flags_at_token_boundary(
    parser: FalyxParser,
) -> None:
    parser.add_option("--region", "-r")

    suggestions, expecting_value = parser.suggest_next(
        ["--"],
        cursor_at_end_of_token=False,
    )

    assert "--help" in suggestions
    assert "--verbose" in suggestions
    assert "--debug-hooks" in suggestions
    assert "--never-prompt" in suggestions
    assert "--region" in suggestions
    assert expecting_value is False


def test_suggest_next_suggests_choice_values_after_store_option(
    parser: FalyxParser,
) -> None:
    parser.add_option("--region", choices=["us-east", "us-west"])

    suggestions, expecting_value = parser.suggest_next(
        ["--region"],
        cursor_at_end_of_token=True,
    )

    assert suggestions == ["us-east", "us-west"]
    assert expecting_value is True


def test_suggest_next_filters_choice_values_by_prefix(parser: FalyxParser) -> None:
    parser.add_option("--region", choices=["us-east", "us-west", "eu-central"])

    suggestions, expecting_value = parser.suggest_next(
        ["--region", "us-e"],
        cursor_at_end_of_token=False,
    )

    assert suggestions == ["us-east"]
    assert expecting_value is True


def test_suggest_next_uses_custom_value_suggestions(parser: FalyxParser) -> None:
    parser.add_option("--profile", suggestions=["dev", "prod", "staging"])

    suggestions, expecting_value = parser.suggest_next(
        ["--profile", "pr"],
        cursor_at_end_of_token=False,
    )

    assert suggestions == ["prod"]
    assert expecting_value is True


def test_suggest_next_excludes_consumed_options(parser: FalyxParser) -> None:
    parser.add_option("--region", choices=["us-east", "us-west"])

    parser.parse_args(["--region", "us-east"])
    suggestions, expecting_value = parser.suggest_next(
        ["-"],
        cursor_at_end_of_token=False,
    )

    assert "--region" not in suggestions
    assert "-r" not in suggestions
    assert expecting_value is False


def test_add_tldr_example_registers_example_and_tldr_option(
    parser: FalyxParser,
) -> None:
    parser.add_tldr_example(
        entry_key="D",
        usage="--region us-east",
        description="Deploy to us-east",
    )

    assert parser.tldr_option is not None
    assert "--tldr" in parser._options_by_dest
    assert parser._tldr_examples == [
        FalyxTLDRExample(
            entry_key="D",
            usage="--region us-east",
            description="Deploy to us-east",
        )
    ]


def test_add_tldr_example_rejects_unknown_entry(parser: FalyxParser) -> None:
    with pytest.raises(EntryNotFoundError) as error:
        parser.add_tldr_example(
            entry_key="depoy",
            usage="",
            description="Typo example",
        )

    assert error.value.unknown_name == "depoy"
    assert error.value.suggestions == ["DEPLOY"]


def test_add_tldr_examples_accepts_dataclass_instances(
    parser: FalyxParser,
) -> None:
    example = FalyxTLDRExample(
        entry_key="deploy",
        usage="--region us-east",
        description="Deploy to us-east",
    )

    parser.add_tldr_examples([example])

    assert parser.tldr_option is not None
    assert parser._tldr_examples == [example]


def test_add_tldr_examples_accepts_three_tuple_examples(
    parser: FalyxParser,
) -> None:
    parser.add_tldr_examples(
        [
            ("deploy", "--region us-east", "Deploy to us-east"),
        ]
    )

    assert parser.tldr_option is not None
    assert parser._tldr_examples == [
        FalyxTLDRExample(
            entry_key="deploy",
            usage="--region us-east",
            description="Deploy to us-east",
        )
    ]


def test_add_tldr_examples_rejects_invalid_tuple_shape(
    parser: FalyxParser,
) -> None:
    with pytest.raises(FalyxOptionError, match="invalid TLDR example format"):
        parser.add_tldr_examples([("deploy", "missing description")])


def test_add_tldr_examples_rejects_unknown_entry(parser: FalyxParser) -> None:
    with pytest.raises(EntryNotFoundError) as error:
        parser.add_tldr_examples(
            [
                ("depoy", "--region us-east", "Typo example"),
            ]
        )

    with pytest.raises(EntryNotFoundError) as error:
        parser.add_tldr_examples(
            [
                FalyxTLDRExample(
                    entry_key="depoy",
                    usage="--region us-east",
                    description="Typo example",
                )
            ]
        )

    assert error.value.unknown_name == "depoy"
    assert error.value.suggestions == ["DEPLOY"]


def test_store_bool_optional_registers_positive_and_negative_flags(
    parser: FalyxParser,
) -> None:
    parser.add_option("--cache", action="store_bool_optional")

    assert "--cache" in parser._options_by_dest
    assert "--no-cache" in parser._options_by_dest

    result = parser.parse_args([])
    assert result.namespace_defaults["cache"] is None

    result = parser.parse_args(["--cache"])
    assert result.namespace_options["cache"] is True

    result = parser.parse_args(["--no-cache"])
    assert result.namespace_options["cache"] is False


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("--cache", True),
        ("--no-cache", False),
    ],
)
def test_parse_args_store_bool_optional_intended_behavior(
    parser: FalyxParser,
    flag: str,
    expected: bool,
) -> None:
    parser.add_option("--cache", action="store_bool_optional")

    result = parser.parse_args([flag])

    assert result.namespace_options["cache"] is expected


def test_parse_args_store_bool_optional_rejects_multiple_flags(
    parser: FalyxParser,
) -> None:
    with pytest.raises(
        FalyxOptionError, match="store_bool_optional action can only have a single flag"
    ):
        parser.add_option("--cache", "-c", action="store_bool_optional")


def test_parse_args_store_bool_optional_rejects_short_flags(parser: FalyxParser) -> None:
    with pytest.raises(
        FalyxOptionError, match="store_bool_optional action must use a long flag"
    ):
        parser.add_option("-c", action="store_bool_optional")


def test_parse_args_long_root_flags(parser: FalyxParser) -> None:
    result = parser.parse_args(["--verbose", "--debug-hooks", "--never-prompt", "deploy"])

    assert result.root_options == {
        "verbose": True,
        "debug_hooks": True,
        "never_prompt": True,
    }
    assert result.namespace_options == {}
    assert result.remaining_argv == ["deploy"]


@pytest.mark.parametrize("help_flag", ["-h", "--help"])
def test_parse_args_forwards_help_after_route_boundary(
    parser: FalyxParser,
    help_flag: str,
) -> None:
    result = parser.parse_args(["deploy", help_flag])

    assert result.mode is FalyxMode.COMMAND
    assert result.help is False
    assert result.namespace_options == {}
    assert result.remaining_argv == ["deploy", help_flag]


def test_parse_args_short_tldr_flag_sets_help_mode_after_tldr_registered(
    parser: FalyxParser,
) -> None:
    parser.add_tldr_example(
        entry_key="D",
        usage="--region us-east",
        description="Deploy to us-east",
    )

    result = parser.parse_args(["-T"])

    assert result.mode is FalyxMode.HELP
    assert result.tldr is True
    assert result.namespace_options["tldr"] is True


def test_add_tldr_examples_registers_tldr_option_only_once(
    parser: FalyxParser,
) -> None:
    parser.add_tldr_example(
        entry_key="deploy",
        usage="--region us-east",
        description="Deploy to us-east",
    )
    parser.add_tldr_example(
        entry_key="deploy",
        usage="--region us-west",
        description="Deploy to us-west",
    )

    tldr_options = [option for option in parser.get_options() if option.dest == "tldr"]

    assert len(tldr_options) == 1
    assert parser.get_flags().count("--tldr") == 1
    assert len(parser._tldr_examples) == 2


def test_parse_args_resets_consumed_option_state_between_parses(
    parser: FalyxParser,
) -> None:
    parser.add_option("--region", "-r", choices=["us-east", "us-west"])

    parser.parse_args(["--region", "us-east"])
    suggestions, _ = parser.suggest_next(["-"], cursor_at_end_of_token=False)
    assert "--region" not in suggestions

    parser.parse_args([])
    suggestions, expecting_value = parser.suggest_next(
        ["--r"],
        cursor_at_end_of_token=False,
    )

    assert suggestions == ["--region"]
    assert expecting_value is False


def test_disabled_reserved_root_options_are_omitted_from_defaults() -> None:
    parser = FalyxParser(
        Falyx(
            disable_verbose_option=True,
            disable_debug_hooks_option=True,
            disable_never_prompt_option=True,
        )
    )

    result = parser.parse_args([])

    assert result.root_defaults == {}
    assert result.namespace_defaults["help"] is False


def test_parse_args_typed_choices_are_compared_after_coercion(
    parser: FalyxParser,
) -> None:
    parser.add_option("--retries", type=int, choices=["1", "2"])

    result = parser.parse_args(["--retries", "1"])

    assert result.namespace_options["retries"] == 1


def test_add_option_rejects_dict_choices(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="choices cannot be a dict"):
        parser.add_option("--region", choices={"east": "us-east"})


def test_add_option_rejects_non_iterable_choices(parser: FalyxParser) -> None:
    with pytest.raises(FalyxOptionError, match="choices must be iterable"):
        parser.add_option("--region", choices=1)


@pytest.mark.parametrize("flag", ["--verbose", "--debug-hooks", "--never-prompt"])
def test_suggest_next_does_not_expect_value_for_root_boolean_flags(
    parser: FalyxParser,
    flag: str,
) -> None:
    suggestions, expecting_value = parser.suggest_next(
        [flag],
        cursor_at_end_of_token=True,
    )

    assert suggestions == []
    assert expecting_value is False


def test_add_option_normalizes_typed_choices(parser: FalyxParser) -> None:
    option = parser.add_option("--retries", type=int, choices=["1", "2"])

    assert option.choices == [1, 2]


def test_parse_args_accepts_value_matching_normalized_typed_choice(
    parser: FalyxParser,
) -> None:
    parser.add_option("--retries", type=int, choices=["1", "2"])

    result = parser.parse_args(["--retries", "1"])

    assert result.namespace_options["retries"] == 1


def test_add_option_normalizes_typed_default_before_choice_check(
    parser: FalyxParser,
) -> None:
    parser.add_option("--retries", type=int, choices=["1", "2"], default="1")

    result = parser.parse_args([])

    assert result.namespace_defaults["retries"] == 1


def test_add_option_returns_registered_option(parser: FalyxParser) -> None:
    option = parser.add_option(
        "--retries",
        type=int,
        default="1",
        choices=["1", "2"],
    )

    assert isinstance(option, Option)
    assert option.dest == "retries"
    assert option.default == 1
    assert option.choices == [1, 2]
    assert option in parser.get_options()


def test_add_option_store_bool_optional_returns_primary_option(
    parser: FalyxParser,
) -> None:
    option = parser.add_option("--cache", action="store_bool_optional")

    assert option.dest == "cache"
    assert option.flags == ("--cache",)
    assert "--cache" in parser._options_by_dest
    assert "--no-cache" in parser._options_by_dest
