import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import words_validator


def test_words_validator_accepts_valid_words():
    validator = words_validator(["hello", "world", "falyx"])
    for valid in ["hello", "world", "falyx"]:
        validator.validate(Document(valid))  # should not raise


@pytest.mark.parametrize("invalid", ["yes", "no", "maybe", "", "1"])
def test_words_validator_rejects_invalid(invalid):
    validator = words_validator(["hello", "world", "falyx"])
    with pytest.raises(ValidationError):
        validator.validate(Document(invalid))
