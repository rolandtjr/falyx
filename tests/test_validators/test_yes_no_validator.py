import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import yes_no_validator


def test_yes_no_validator_accepts_y_and_n():
    validator = yes_no_validator()
    for valid in ["Y", "y", "N", "n"]:
        validator.validate(Document(valid))


@pytest.mark.parametrize("invalid", ["yes", "no", "maybe", "", "1"])
def test_yes_no_validator_rejects_invalid(invalid):
    validator = yes_no_validator()
    with pytest.raises(ValidationError):
        validator.validate(Document(invalid))
