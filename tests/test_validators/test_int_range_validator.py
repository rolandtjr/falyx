import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import int_range_validator


def test_int_range_validator_accepts_valid_numbers():
    validator = int_range_validator(1, 10)
    for valid in ["1", "5", "10"]:
        validator.validate(Document(valid))


@pytest.mark.parametrize("invalid", ["0", "11", "5.5", "hello", "-1", ""])
def test_int_range_validator_rejects_invalid(invalid):
    validator = int_range_validator(1, 10)
    with pytest.raises(ValidationError):
        validator.validate(Document(invalid))


def test_int_range_validator_edge_cases():
    validator = int_range_validator(1, 10)
    for valid in ["1", "10"]:
        validator.validate(Document(valid))
