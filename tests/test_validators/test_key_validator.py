import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import key_validator


def test_key_validator_accepts_valid_keys():
    validator = key_validator(["A", "B", "Z"])
    for valid in ["A", "B", "Z"]:
        validator.validate(Document(valid))


@pytest.mark.parametrize("invalid", ["Y", "D", "C", "", "1", "AB", "ZB"])
def test_key_validator_rejects_invalid(invalid):
    validator = key_validator(["A", "B", "Z"])
    with pytest.raises(ValidationError):
        validator.validate(Document(invalid))
