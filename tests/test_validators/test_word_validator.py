import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import word_validator


def test_word_validator_accepts_valid_words():
    validator = word_validator("apple")
    validator.validate(Document("apple"))
    validator.validate(Document("N"))


def test_word_validator_accepts_case_insensitive():
    validator = word_validator("banana")
    validator.validate(Document("BANANA"))
    validator.validate(Document("banana"))


def test_word_validator_rejects_n():
    with pytest.raises(ValueError):
        word_validator("N")


@pytest.mark.parametrize("invalid", ["yes", "no", "maybe", "", "1"])
def test_word_validator_rejects_invalid(invalid):
    validator = word_validator("apple")
    with pytest.raises(ValidationError):
        validator.validate(Document(invalid))
