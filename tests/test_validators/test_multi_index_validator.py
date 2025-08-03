import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import MultiIndexValidator


def test_multi_index_validator_accepts_valid_indices():
    validator = MultiIndexValidator(
        1, 5, number_selections=3, separator=",", allow_duplicates=False, cancel_key="C"
    )
    for valid in ["1,2,3", "2,3,4", "1,4,5"]:
        validator.validate(Document(valid))


def test_multi_index_validator_rejects_invalid_indices():
    validator = MultiIndexValidator(
        1, 5, number_selections=3, separator=",", allow_duplicates=False, cancel_key="C"
    )
    with pytest.raises(ValidationError):
        validator.validate(Document("A,!,F"))
    with pytest.raises(ValidationError):
        validator.validate(Document("0,6,7"))
    with pytest.raises(ValidationError):
        validator.validate(Document("1,2,2"))


def test_multi_index_validator_rejects_invalid_number_of_selections():
    validator = MultiIndexValidator(
        1, 5, number_selections=3, separator=",", allow_duplicates=False, cancel_key="C"
    )
    with pytest.raises(ValidationError):
        validator.validate(Document("1,2"))
    with pytest.raises(ValidationError):
        validator.validate(Document("1,2,3,4"))
    validator = MultiIndexValidator(
        1, 5, number_selections=1, separator=",", allow_duplicates=False, cancel_key="C"
    )
    validator.validate(Document("1"))
    with pytest.raises(ValidationError):
        validator.validate(Document("2,3"))


def test_multi_index_validator_cancel_key():
    validator = MultiIndexValidator(
        1, 5, number_selections=3, separator=",", allow_duplicates=False, cancel_key="C"
    )
    validator.validate(Document("C"))


def test_multi_index_validator_cancel_alone():
    validator = MultiIndexValidator(
        1, 5, number_selections=3, separator=",", allow_duplicates=False, cancel_key="C"
    )
    with pytest.raises(ValidationError):
        validator.validate(Document("1,C"))


def test_multi_index_validator_empty_input():
    validator = MultiIndexValidator(
        1, 5, number_selections=3, separator=",", allow_duplicates=False, cancel_key="C"
    )
    with pytest.raises(ValidationError):
        validator.validate(Document(""))


def test_multi_index_validator_error_message_for_duplicates():
    validator = MultiIndexValidator(
        1, 5, number_selections=3, separator=",", allow_duplicates=False, cancel_key="C"
    )
    with pytest.raises(ValidationError) as e:
        validator.validate(Document("1,1,2"))
    assert "Duplicate selection" in str(e.value)
