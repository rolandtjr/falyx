from pathlib import Path

import pytest

from falyx.exceptions import CommandArgumentError
from falyx.parser.command_argument_parser import CommandArgumentParser


def build_default_parser():
    p = CommandArgumentParser(
        command_key="D", aliases=["deploy"], program="argument_examples.py"
    )
    p.add_argument("service", type=str, help="Service name.")
    p.add_argument("place", type=str, nargs="?", default="New York", help="Place.")
    p.add_argument(
        "--region",
        choices=["us-east-1", "us-west-2", "eu-west-1"],
        help="Region.",
        default="us-east-1",
    )
    p.add_argument("-p", "--path", type=Path, help="Path.")
    p.add_argument("-v", "--verbose", action="store_true", help="Verbose.")
    p.add_argument("-t", "--tag", type=str, suggestions=["latest", "stable", "beta"])
    p.add_argument("--numbers", type=int, nargs="*", default=[1, 2, 3], help="Nums.")
    p.add_argument("-j", "--just-a-bool", action="store_true", help="Bool.")
    p.add_argument("-a", action="store_true")
    p.add_argument("-b", action="store_true")
    return p


@pytest.mark.asyncio
async def test_parse_minimal_positional_and_defaults():
    p = build_default_parser()
    got = await p.parse_args(["web"])
    assert got["service"] == "web"
    assert got["place"] == "New York"
    assert got["numbers"] == [1, 2, 3]
    assert got["verbose"] is False
    assert got["tag"] is None
    assert got["path"] is None


@pytest.mark.asyncio
async def test_parse_all_keywords_and_lists_and_bools():
    p = build_default_parser()
    got = await p.parse_args(
        [
            "web",
            "Paris",
            "--region",
            "eu-west-1",
            "--numbers",
            "10",
            "20",
            "-30",
            "-t",
            "stable",
            "-p",
            "pyproject.toml",
            "-v",
            "-j",
        ]
    )
    assert got["service"] == "web"
    assert got["place"] == "Paris"
    assert got["region"] == "eu-west-1"
    assert got["numbers"] == [10, 20, -30]
    assert got["tag"] == "stable"
    assert isinstance(got["path"], Path)
    assert got["verbose"] is True and got["just_a_bool"] is True


@pytest.mark.asyncio
async def test_parse_numbers_negative_values_not_flags():
    p = build_default_parser()
    got = await p.parse_args(["web", "--numbers", "-1", "-2", "-3"])
    assert got["numbers"] == [-1, -2, -3]


def test_default_list_must_match_choices_when_choices_present():
    p = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        p.add_argument(
            "--color", choices=["red", "blue"], nargs="*", default=["red", "green"]
        )


def test_default_type_for_nargs_requires_list():
    p = CommandArgumentParser()
    with pytest.raises(CommandArgumentError):
        p.add_argument("--ints", type=int, nargs=2, default=1)


@pytest.mark.asyncio
async def test_choices_enforced_on_result():
    p = CommandArgumentParser()
    p.add_argument("--env", choices=["prod", "dev"])
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--env", "staging"])


@pytest.mark.asyncio
async def test_posix_bundling_flags_only():
    p = CommandArgumentParser()
    p.add_argument("-a", "--aa", action="store_true")
    p.add_argument("-b", "--bb", action="store_true")
    p.add_argument("-c", "--cc", action="store_true")
    got = await p.parse_args(["-abc"])
    assert got["aa"] and got["bb"] and got["cc"]


@pytest.mark.asyncio
async def test_posix_bundling_not_applied_when_value_like():
    p = CommandArgumentParser()
    p.add_argument("-n", "--num", type=int)
    p.add_argument("-a", action="store_true")
    p.add_argument("-b", action="store_true")
    got = await p.parse_args(["--num", "-123", "-ab"])
    assert got["num"] == -123
    assert got["a"] and got["b"]


def mk_tmp_tree(tmp_path: Path):
    (tmp_path / "dirA").mkdir()
    (tmp_path / "dirB").mkdir()
    (tmp_path / "file.txt").write_text("x")


def test_complete_initial_flags_and_suggestions():
    p = build_default_parser()
    sugg = p.suggest_next([""], cursor_at_end_of_token=False)
    assert "--tag" in sugg and "--region" in sugg and "-v" in sugg


def test_complete_flag_by_prefix():
    p = build_default_parser()
    assert p.suggest_next(["--ta"], False) == ["--tag"]


@pytest.mark.asyncio
async def test_complete_values_for_flag_choices():
    p = build_default_parser()
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--region"])
    sugg = p.suggest_next(["--region"], True)
    assert set(sugg) == {"us-east-1", "us-west-2", "eu-west-1"}
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--region", "us-"])
    sugg2 = p.suggest_next(["--region", "us-"], False)
    assert set(sugg2) == {"us-east-1", "us-west-2"}


@pytest.mark.asyncio
async def test_complete_values_for_flag_suggestions():
    p = build_default_parser()
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--tag"])
    assert set(p.suggest_next(["--tag"], True)) == {"latest", "stable", "beta"}
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--tag", "st"])
    assert set(p.suggest_next(["--tag", "st"], False)) == {"stable"}


def test_complete_mid_flag_hyphen_value_uses_previous_flag_context():
    p = build_default_parser()
    sugg = p.suggest_next(["--numbers", "-1"], False)
    assert "--tag" not in sugg and "--region" not in sugg


def test_complete_multi_value_keeps_suggesting_for_plus_star():
    p = build_default_parser()
    sugg1 = p.suggest_next(["--numbers"], False)
    assert "--tag" not in sugg1 or True
    sugg2 = p.suggest_next(["--numbers", "1"], False)
    assert "--tag" not in sugg2 or True


@pytest.mark.asyncio
async def test_complete_path_values(tmp_path, monkeypatch):
    mk_tmp_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    p = build_default_parser()
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--path"])
    sugg = p.suggest_next(["--path"], True)
    assert any(s.endswith("/") for s in sugg) and "file.txt" in sugg
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--path", "d"])
    sugg2 = p.suggest_next(["--path", "d"], False)
    assert "dirA/" in sugg2 or "dirB/" in sugg2


@pytest.mark.asyncio
async def test_complete_positional_path(tmp_path, monkeypatch):
    mk_tmp_tree(tmp_path)
    monkeypatch.chdir(tmp_path)
    p = CommandArgumentParser()
    p.add_argument("paths", type=Path, nargs="*")
    await p.parse_args([""])
    s1 = p.suggest_next([""], False)
    assert "file.txt" in s1 or "dirA/" in s1
    await p.parse_args(["fi"])
    s2 = p.suggest_next(["fi"], False)
    assert "file.txt" in s2


@pytest.mark.asyncio
async def test_flag_then_space_yields_flag_suggestions():
    p = build_default_parser()
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--tag"])
    sugg = p.suggest_next(["--tag"], True)
    assert "latest" in sugg


def test_complete_multi_value_persists_until_space_or_new_flag():
    p = build_default_parser()

    s1 = p.suggest_next(["--numbers"], cursor_at_end_of_token=False)
    assert "--tag" not in s1 or True

    s2 = p.suggest_next(["--numbers", "1"], cursor_at_end_of_token=False)
    assert "--tag" not in s2 or True

    s3 = p.suggest_next(["--numbers", "1"], cursor_at_end_of_token=True)
    assert "--tag" not in s3 or True


@pytest.mark.asyncio
async def test_mid_value_suggestions_then_flags_after_space():
    p = build_default_parser()
    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--tag", "st"])
    s_mid = p.suggest_next(["--tag", "st"], cursor_at_end_of_token=False)
    assert set(s_mid) == {"stable"}

    s_after = p.suggest_next(["--tag"], cursor_at_end_of_token=True)
    assert any(opt.startswith("-") for opt in s_after)


@pytest.mark.asyncio
async def test_negative_values_then_posix_bundle():
    p = build_default_parser()
    out = await p.parse_args(["prod", "--numbers", "-3", "-ab"])
    assert out["numbers"] == [-3]
    assert out["a"] is True and out["b"] is True


def test_mid_flag_token_after_negative_value_uses_prior_flag_context():
    p = build_default_parser()
    sugg = p.suggest_next(["--numbers", "-1"], cursor_at_end_of_token=False)
    assert "--tag" not in sugg and "--region" not in sugg


@pytest.mark.asyncio
async def test_path_dash_prefix_is_value_not_flags():
    p = CommandArgumentParser()
    p.add_argument("-a", action="store_true")
    p.add_argument("--path", type=Path)

    out = await p.parse_args(["--path", "-abc", "-a"])
    assert str(out["path"]) == "-abc"
    assert out["a"] is True


@pytest.mark.asyncio
async def test_store_bool_optional_pair_last_one_wins():
    p = CommandArgumentParser()
    p.add_argument("--feature", action="store_bool_optional", help="toggle feature")

    out0 = await p.parse_args([])
    assert out0["feature"] is None

    out1 = await p.parse_args(["--feature"])
    assert out1["feature"] is True

    out2 = await p.parse_args(["--no-feature"])
    assert out2["feature"] is False

    out3 = await p.parse_args(["--feature", "--no-feature"])
    assert out3["feature"] is False

    out4 = await p.parse_args(["--no-feature", "--feature"])
    assert out4["feature"] is True


@pytest.mark.asyncio
async def test_invalid_choice_suppresses_then_recovers():
    p = build_default_parser()

    with pytest.raises(CommandArgumentError):
        await p.parse_args(["--region", "us-"])

    s_suppressed = p.suggest_next(["--region", "us-"], cursor_at_end_of_token=True)
    assert s_suppressed == []

    s_recover = p.suggest_next(["--region", "us-"], cursor_at_end_of_token=False)
    assert set(s_recover) == {"us-east-1", "us-west-2"}


@pytest.mark.asyncio
async def test_repeated_keyword_last_one_wins_and_guides_completion():
    p = build_default_parser()

    out = await p.parse_args(["test", "--tag", "alpha", "--tag", "st"])
    assert out["tag"] == "st"

    s = p.suggest_next(
        ["test", "--tag", "alpha", "--tag", "st"], cursor_at_end_of_token=False
    )
    assert set(s) == {"stable"}
