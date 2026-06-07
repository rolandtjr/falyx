from falyx.console import console
from falyx.execution_option import ExecutionOption
from falyx.options_manager import OptionsManager
from falyx.parser import CommandArgumentParser
from falyx.parser.parser_types import TLDRExample


def build_parser() -> CommandArgumentParser:
    parser = CommandArgumentParser(
        command_key="D",
        command_description="Deploy",
        help_text="Deploy something.",
        help_epilog="More help text.",
        aliases=["deploy"],
        program="source",
        options_manager=OptionsManager(),
    )

    parser.add_argument("--region", choices=["us-east", "us-west"], default="us-east")
    parser.add_argument("target")

    group = parser.add_argument_group("auth", description="Authentication options")
    group.add_argument("--profile", suggestions=["dev", "prod"])

    mutex = parser.add_mutually_exclusive_group(
        "mode",
        required=False,
        description="Execution mode",
    )
    mutex.add_argument("--dry-run", action="store_true")
    mutex.add_argument("--apply", action="store_true")

    parser.add_tldr_examples(
        [
            ("target-1 --region us-east", "Deploy target-1 to us-east."),
            ("target-2 --dry-run", "Preview target-2 without executing."),
        ]
    )

    parser.enable_execution_options(
        frozenset(
            {
                ExecutionOption.SUMMARY,
                ExecutionOption.RETRY,
                ExecutionOption.CONFIRM,
            }
        )
    )
    return parser


def build_parser_with_tldr_examples() -> CommandArgumentParser:
    parser = build_parser()
    parser.add_tldr_examples(
        [
            ("target-3 --profile dev", "Deploy target-3 using dev profile."),
        ]
    )
    return parser


def build_parser_with_groups() -> CommandArgumentParser:
    parser = build_parser()
    group = parser.add_argument_group("output", description="Output options")
    group.add_argument("--json", action="store_true")
    return parser


def build_parser_with_execution_options() -> CommandArgumentParser:
    parser = build_parser()
    parser.enable_execution_options(
        frozenset(
            {
                ExecutionOption.SUMMARY,
                ExecutionOption.RETRY,
                ExecutionOption.CONFIRM,
            }
        )
    )
    return parser


def test_clone_with_overrides_preserves_core_metadata():
    original = build_parser()
    new_options = OptionsManager()

    cloned = original.clone_with_overrides(
        command_key="X",
        command_description="Execute",
        help_text="Execute something else.",
        help_epilog="Different epilog.",
        aliases=["execute"],
        program="target",
        options_manager=new_options,
    )

    assert cloned is not original
    assert cloned.command_key == "X"
    assert cloned.command_description == "Execute"
    assert cloned.help_text == "Execute something else."
    assert cloned.help_epilog == "Different epilog."
    assert cloned.aliases == ["execute"]
    assert cloned.program == "target"
    assert cloned.options_manager is new_options


def test_clone_with_overrides_keeps_execution_options_enabled_without_double_registration():
    original = build_parser()
    cloned = original.clone_with_overrides()

    summary = cloned.get_argument("summary")
    retries = cloned.get_argument("retries")
    retry_delay = cloned.get_argument("retry_delay")
    retry_backoff = cloned.get_argument("retry_backoff")
    force_confirm = cloned.get_argument("force_confirm")
    skip_confirm = cloned.get_argument("skip_confirm")

    assert summary is not None
    assert retries is not None
    assert retry_delay is not None
    assert retry_backoff is not None
    assert force_confirm is not None
    assert skip_confirm is not None

    # Re-enabling on the clone should be idempotent, not duplicate flags/dests.
    cloned.enable_execution_options(
        frozenset(
            {
                ExecutionOption.SUMMARY,
                ExecutionOption.RETRY,
                ExecutionOption.CONFIRM,
            }
        )
    )

    assert len([arg for arg in cloned._arguments if arg.dest == "summary"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "retries"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "retry_delay"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "retry_backoff"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "force_confirm"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "skip_confirm"]) == 1


def test_clone_with_overrides_preserves_groups_and_mutex_groups():
    original = build_parser()
    cloned = original.clone_with_overrides()

    assert "auth" in cloned._argument_groups
    assert "mode" in cloned._mutex_groups

    assert cloned._arg_group_by_dest["profile"] == "auth"
    assert cloned._mutex_group_by_dest["dry_run"] == "mode"
    assert cloned._mutex_group_by_dest["apply"] == "mode"

    assert cloned.get_argument("profile") is not None
    assert cloned.get_argument("dry_run") is not None
    assert cloned.get_argument("apply") is not None


def test_clone_with_overrides_preserves_tldr_examples_and_help_flags():
    original = build_parser()
    cloned = original.clone_with_overrides()

    assert cloned.help_text == original.help_text
    assert cloned.help_epilog == original.help_epilog
    assert cloned.get_argument("help") is not None
    assert cloned.get_argument("tldr") is not None
    assert cloned._tldr_examples == original._tldr_examples
    assert cloned._tldr_examples is not original._tldr_examples


def test_clone_with_overrides_does_not_share_argument_registries_with_original():
    original = build_parser()
    cloned = original.clone_with_overrides()

    assert cloned._arguments is not original._arguments
    assert cloned._positional is not original._positional
    assert cloned._keyword is not original._keyword
    assert cloned._keyword_list is not original._keyword_list
    assert cloned._flag_map is not original._flag_map
    assert cloned._dest_set is not original._dest_set
    assert cloned._execution_dests is not original._execution_dests

    cloned.add_argument("--new-flag", default="x")

    assert cloned.get_argument("new_flag") is not None
    assert original.get_argument("new_flag") is None


def test_clone_with_overrides_does_not_share_group_registries_with_original():
    original = build_parser()
    cloned = original.clone_with_overrides()

    assert cloned._argument_groups is not original._argument_groups
    assert cloned._mutex_groups is not original._mutex_groups
    assert cloned._arg_group_by_dest is not original._arg_group_by_dest
    assert cloned._mutex_group_by_dest is not original._mutex_group_by_dest

    cloned_group = cloned.add_argument_group("output", description="Output options")
    cloned_group.add_argument("--json", action="store_true")

    assert "output" in cloned._argument_groups
    assert "output" not in original._argument_groups
    assert cloned.get_argument("json") is not None
    assert original.get_argument("json") is None


def test_clone_with_overrides_reuses_no_mutable_group_objects():
    original = build_parser()
    cloned = original.clone_with_overrides()

    # These should ideally be distinct objects too, not just distinct dicts.
    assert cloned._argument_groups["auth"] is not original._argument_groups["auth"]
    assert cloned._mutex_groups["mode"] is not original._mutex_groups["mode"]


def test_clone_with_overrides_reuses_no_mutable_argument_objects():
    original = build_parser()
    cloned = original.clone_with_overrides()

    # Strict contract: cloned parser should not share Argument instances either.
    assert cloned.get_argument("region") is not original.get_argument("region")
    assert cloned.get_argument("target") is not original.get_argument("target")
    assert cloned.get_argument("profile") is not original.get_argument("profile")


def test_clone_with_overrides_uses_new_options_manager():
    original = build_parser()
    new_options = OptionsManager()

    cloned = original.clone_with_overrides(options_manager=new_options)

    assert cloned.options_manager is new_options
    assert original.options_manager is not new_options


def test_clone_with_overrides_has_single_help_and_single_tldr_argument():
    parser = build_parser_with_tldr_examples()

    cloned = parser.clone_with_overrides()

    assert len([arg for arg in cloned._arguments if arg.dest == "help"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "tldr"]) == 1
    assert cloned.get_argument("help") is not None
    assert cloned.get_argument("tldr") is not None


def test_clone_with_overrides_copies_tldr_examples():
    parser = build_parser_with_tldr_examples()

    cloned = parser.clone_with_overrides()

    assert cloned._tldr_examples == parser._tldr_examples
    assert cloned._tldr_examples is not parser._tldr_examples
    assert all(c is not o for c, o in zip(cloned._tldr_examples, parser._tldr_examples))


def test_clone_with_overrides_copies_explicit_tldr_examples():
    parser = build_parser()
    examples = [TLDRExample("foo", "bar")]

    cloned = parser.clone_with_overrides(tldr_examples=examples)

    assert cloned._tldr_examples == examples
    assert cloned._tldr_examples is not examples


def test_clone_with_overrides_does_not_share_aliases_list():
    parser = build_parser()
    cloned = parser.clone_with_overrides()

    assert cloned.aliases == parser.aliases
    assert cloned.aliases is not parser.aliases

    cloned.aliases.append("new-alias")
    assert "new-alias" not in parser.aliases


def test_clone_with_overrides_rebuilds_group_membership_without_duplicates():
    parser = build_parser_with_groups()
    cloned = parser.clone_with_overrides()

    assert cloned._argument_groups["auth"].dests == {"profile"}
    assert set(cloned._mutex_groups["mode"].dests) == {"dry_run", "apply"}
    assert len(cloned._mutex_groups["mode"].dests) == 2


def test_clone_with_overrides_does_not_share_group_objects():
    parser = build_parser_with_groups()
    cloned = parser.clone_with_overrides()

    assert cloned._argument_groups is not parser._argument_groups
    assert cloned._mutex_groups is not parser._mutex_groups
    assert cloned._argument_groups["auth"] is not parser._argument_groups["auth"]
    assert cloned._mutex_groups["mode"] is not parser._mutex_groups["mode"]


def test_clone_with_overrides_does_not_share_argument_objects():
    parser = build_parser()
    cloned = parser.clone_with_overrides()

    for original_arg in parser._arguments:
        cloned_arg = cloned.get_argument(original_arg.dest)
        console.print(original_arg)
        console.print(cloned_arg)
        assert cloned_arg is not None
        assert cloned_arg is not original_arg
        assert cloned_arg == original_arg


def test_clone_with_overrides_internal_registries_point_to_cloned_arguments():
    parser = build_parser()
    cloned = parser.clone_with_overrides()

    for arg in cloned._arguments:
        for flag in arg.flags:
            assert cloned._flag_map[flag] is arg
            if not arg.positional:
                assert cloned._keyword[flag] is arg

        if arg.positional:
            assert cloned._positional[arg.dest] is arg
        else:
            assert arg in cloned._keyword_list


def test_clone_with_overrides_preserves_execution_option_state_without_duplication():
    parser = build_parser_with_execution_options()
    cloned = parser.clone_with_overrides()

    assert cloned._summary_enabled is True
    assert cloned._retries_enabled is True
    assert cloned._confirm_enabled is True
    assert cloned._execution_dests == parser._execution_dests
    assert cloned._execution_dests is not parser._execution_dests

    cloned.enable_execution_options(
        frozenset(
            {
                ExecutionOption.SUMMARY,
                ExecutionOption.RETRY,
                ExecutionOption.CONFIRM,
            }
        )
    )

    assert len([arg for arg in cloned._arguments if arg.dest == "summary"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "retries"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "retry_delay"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "retry_backoff"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "force_confirm"]) == 1
    assert len([arg for arg in cloned._arguments if arg.dest == "skip_confirm"]) == 1


def test_clone_with_overrides_preserves_runner_and_help_mode_flags():
    parser = build_parser()
    parser.is_runner_mode = True
    parser.mark_as_help_command()

    cloned = parser.clone_with_overrides()

    assert cloned.is_runner_mode is True
    assert cloned._is_help_command is True


def test_clone_with_overrides_mutating_clone_does_not_mutate_original():
    parser = build_parser()
    cloned = parser.clone_with_overrides()

    cloned.add_argument("--new-flag", default="x")

    assert cloned.get_argument("new_flag") is not None
    assert parser.get_argument("new_flag") is None
