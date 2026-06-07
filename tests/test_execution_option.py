import pytest

from falyx.execution_option import ExecutionOption


def test_execution_option_accepts_valid_string_values():
    assert ExecutionOption("summary") == ExecutionOption.SUMMARY
    assert ExecutionOption("retry") == ExecutionOption.RETRY
    assert ExecutionOption("confirm") == ExecutionOption.CONFIRM


def test_execution_option_rejects_invalid_string():
    with pytest.raises(ValueError, match="Invalid ExecutionOption: 'invalid'"):
        ExecutionOption("invalid")


def test_execution_option_normalizes_case_and_whitespace():
    assert ExecutionOption("  SUMMARY  ") == ExecutionOption.SUMMARY
    assert ExecutionOption("ReTrY") == ExecutionOption.RETRY
    assert ExecutionOption("\tconfirm\n") == ExecutionOption.CONFIRM


def test_execution_option_rejects_non_string():
    with pytest.raises(ValueError, match="Invalid ExecutionOption: 123"):
        ExecutionOption(123)


def test_execution_option_error_lists_valid_values():
    with pytest.raises(ValueError, match="Must be one of: summary, retry, confirm"):
        ExecutionOption("invalid")
