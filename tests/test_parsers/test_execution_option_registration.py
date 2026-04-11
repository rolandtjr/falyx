import pytest

from falyx.exceptions import CommandArgumentError
from falyx.execution_option import ExecutionOption
from falyx.parser import CommandArgumentParser


def test_enable_execution_options_registers_summary_flag():
    parser = CommandArgumentParser()
    parser.enable_execution_options(frozenset({ExecutionOption.SUMMARY}))
    assert "--summary" in parser._flag_map
    assert "--summary" in parser._keyword
    assert "--summary" in parser._flag_map
    assert "summary" in parser._execution_dests


def test_enable_execution_options_registers_retry_flags():
    parser = CommandArgumentParser()
    parser.enable_execution_options(frozenset({ExecutionOption.RETRY}))
    assert "--retries" in parser._flag_map
    assert "--retries" in parser._keyword
    assert "--retries" in parser._flag_map
    assert "retries" in parser._execution_dests
    assert "--retry-delay" in parser._flag_map
    assert "--retry-delay" in parser._keyword
    assert "--retry-delay" in parser._flag_map
    assert "retry_delay" in parser._execution_dests
    assert "--retry-backoff" in parser._flag_map
    assert "--retry-backoff" in parser._keyword
    assert "--retry-backoff" in parser._flag_map
    assert "retry_backoff" in parser._execution_dests


def test_enable_execution_options_registers_confirm_flags():
    parser = CommandArgumentParser()
    parser.enable_execution_options(frozenset({ExecutionOption.CONFIRM}))
    assert "--confirm" in parser._flag_map
    assert "--confirm" in parser._keyword
    assert "--confirm" in parser._flag_map
    assert "force_confirm" in parser._execution_dests
    assert "--skip-confirm" in parser._flag_map
    assert "--skip-confirm" in parser._keyword
    assert "--skip-confirm" in parser._flag_map
    assert "skip_confirm" in parser._execution_dests


def test_register_execution_dest_rejects_duplicates():
    parser = CommandArgumentParser()
    parser.enable_execution_options(frozenset({ExecutionOption.SUMMARY}))
    with pytest.raises(
        CommandArgumentError, match="Destination 'summary' is already defined"
    ):
        parser.add_argument("--summary", action="store_true")

    with pytest.raises(
        CommandArgumentError, match="Destination 'summary' is already defined"
    ):
        parser.enable_execution_options(frozenset({ExecutionOption.SUMMARY}))


@pytest.mark.asyncio
async def test_parse_args_split_with_execution_options_returns_correct_execution_args():
    parser = CommandArgumentParser()
    parser.add_argument("foo", type=int, help="A business argument.")
    parser.add_argument("--bar", type=int, help="A business argument.")
    parser.enable_execution_options(
        frozenset({ExecutionOption.SUMMARY, ExecutionOption.RETRY})
    )

    args, kwargs, execution_args = await parser.parse_args_split(
        ["50", "--bar", "42", "--summary", "--retries", "3"]
    )

    assert args == (50,)
    assert kwargs == {"bar": 42}
    assert execution_args == {
        "summary": True,
        "retries": 3,
        "retry_delay": 0.0,
        "retry_backoff": 0.0,
    }


@pytest.mark.asyncio
async def test_parse_args_split_with_all_execution_options_returns_correct_execution_args():
    parser = CommandArgumentParser()
    parser.add_argument("foo", type=int, help="A business argument.")
    parser.add_argument("--bar", type=int, help="A business argument.")
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
            "50",
            "--bar",
            "42",
            "--summary",
            "--retries",
            "3",
            "--confirm",
        ]
    )

    assert args == (50,)
    assert kwargs == {"bar": 42}
    assert execution_args == {
        "summary": True,
        "retries": 3,
        "retry_delay": 0.0,
        "retry_backoff": 0.0,
        "force_confirm": True,
        "skip_confirm": False,
    }


@pytest.mark.asyncio
async def test_parse_args_split_with_no_execution_options_returns_empty_execution_args():
    parser = CommandArgumentParser()
    parser.add_argument("foo", type=int, help="A business argument.")
    parser.add_argument("--bar", type=int, help="A business argument.")

    args, kwargs, execution_args = await parser.parse_args_split(["50", "--bar", "42"])

    assert args == (50,)
    assert kwargs == {"bar": 42}
    assert execution_args == {}


@pytest.mark.asyncio
async def test_parse_args_split_with_conflicting_execution_option_raises():
    parser = CommandArgumentParser()
    parser.add_argument("--summary", action="store_true", help="A conflicting argument.")
    with pytest.raises(
        CommandArgumentError, match="Destination 'summary' is already defined"
    ):
        parser.enable_execution_options(frozenset({ExecutionOption.SUMMARY}))
