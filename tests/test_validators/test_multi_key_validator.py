import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import MultiKeyValidator


def test_multi_key_validator_accepts_valid_keys():
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=2,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    for valid in ["A,B", "B,C", "A,C"]:
        validator.validate(Document(valid))


def test_multi_key_validator_rejects_invalid_keys():
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=2,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    with pytest.raises(ValidationError):
        validator.validate(Document("D,E,F"))
    with pytest.raises(ValidationError):
        validator.validate(Document("A,B,A"))
    with pytest.raises(ValidationError):
        validator.validate(Document("A,B,C,D"))


def test_multi_key_validator_rejects_invalid_number_of_selections():
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=2,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    with pytest.raises(ValidationError):
        validator.validate(Document("A"))  # Not enough selections
    with pytest.raises(ValidationError):
        validator.validate(Document("A,B,C"))  # Too many selections
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=1,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    validator.validate(Document("A"))  # Exactly one selection is valid
    with pytest.raises(ValidationError):
        validator.validate(Document("B,C"))  # Too many selections


def test_multi_key_validator_cancel_key():
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=2,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    validator.validate(Document("X"))


def test_multi_key_validator_cancel_alone():
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=2,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    with pytest.raises(ValidationError):
        validator.validate(Document("A,X"))


def test_multi_key_validator_empty_input():
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=2,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    with pytest.raises(ValidationError):
        validator.validate(Document(""))


def test_multi_key_validator_error_message_for_duplicates():
    validator = MultiKeyValidator(
        ["A", "B", "C"],
        number_selections=2,
        separator=",",
        allow_duplicates=False,
        cancel_key="X",
    )
    with pytest.raises(ValidationError) as e:
        validator.validate(Document("A,A,B"))
    assert "Duplicate selection" in str(e.value)
