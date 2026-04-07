from falyx import Falyx
from falyx.parser.falyx_parser import FalyxParser, RootOptions


def get_falyx_parser():
    falyx = Falyx()
    return FalyxParser(falyx=falyx)


def test_parse_root_options_empty():
    parser = get_falyx_parser()
    opts, remaining = parser._parse_root_options([])
    assert opts == RootOptions()
    assert remaining == []


def test_parse_root_options_consumes_known_leading_flags():
    parser = get_falyx_parser()
    opts, remaining = parser._parse_root_options(
        ["--verbose", "--never-prompt", "deploy", "--env", "prod"]
    )
    assert opts.verbose is True
    assert opts.never_prompt is True
    assert remaining == ["deploy", "--env", "prod"]


def test_parse_root_options_stops_at_first_non_root_token():
    parser = get_falyx_parser()
    opts, remaining = parser._parse_root_options(["deploy", "--verbose"])
    assert opts == RootOptions()
    assert remaining == ["deploy", "--verbose"]


def test_parse_root_options_supports_help():
    parser = get_falyx_parser()
    opts, remaining = parser._parse_root_options(["--help"])
    assert opts.help is True
    assert remaining == []


def test_parse_root_options_supports_double_dash_separator():
    parser = get_falyx_parser()
    opts, remaining = parser._parse_root_options(
        ["--verbose", "--", "deploy", "--verbose"]
    )
    assert opts.verbose is True
    assert remaining == ["deploy", "--verbose"]
