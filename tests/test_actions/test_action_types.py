import pytest

from falyx.action.action_types import ConfirmType, FileType, SelectionReturnType


def test_file_type_enum():
    """Test if the FileType enum has all expected members."""
    assert FileType.TEXT.value == "text"
    assert FileType.PATH.value == "path"
    assert FileType.JSON.value == "json"
    assert FileType.TOML.value == "toml"
    assert FileType.YAML.value == "yaml"
    assert FileType.CSV.value == "csv"
    assert FileType.TSV.value == "tsv"
    assert FileType.XML.value == "xml"

    assert str(FileType.TEXT) == "text"


def test_file_type_choices():
    """Test if the FileType choices method returns all enum members."""
    choices = FileType.choices()
    assert len(choices) == 8
    assert all(isinstance(choice, FileType) for choice in choices)


def test_file_type_missing():
    """Test if the _missing_ method raises ValueError for invalid values."""
    with pytest.raises(ValueError, match="Invalid FileType: 'invalid'"):
        FileType._missing_("invalid")

    with pytest.raises(ValueError, match="Invalid FileType: 123"):
        FileType._missing_(123)


def test_file_type_aliases():
    """Test if the _get_alias method returns correct aliases."""
    assert FileType._get_alias("file") == "path"
    assert FileType._get_alias("filepath") == "path"
    assert FileType._get_alias("unknown") == "unknown"


def test_file_type_missing_aliases():
    """Test if the _missing_ method handles aliases correctly."""
    assert FileType._missing_("file") == FileType.PATH
    assert FileType._missing_("filepath") == FileType.PATH

    with pytest.raises(ValueError, match="Invalid FileType: 'unknown'"):
        FileType._missing_("unknown")


def test_confirm_type_enum():
    """Test if the ConfirmType enum has all expected members."""
    assert ConfirmType.YES_NO.value == "yes_no"
    assert ConfirmType.YES_CANCEL.value == "yes_cancel"
    assert ConfirmType.YES_NO_CANCEL.value == "yes_no_cancel"
    assert ConfirmType.TYPE_WORD.value == "type_word"
    assert ConfirmType.TYPE_WORD_CANCEL.value == "type_word_cancel"
    assert ConfirmType.OK_CANCEL.value == "ok_cancel"
    assert ConfirmType.ACKNOWLEDGE.value == "acknowledge"

    assert str(ConfirmType.YES_NO) == "yes_no"


def test_confirm_type_choices():
    """Test if the ConfirmType choices method returns all enum members."""
    choices = ConfirmType.choices()
    assert len(choices) == 7
    assert all(isinstance(choice, ConfirmType) for choice in choices)


def test_confirm_type_missing():
    """Test if the _missing_ method raises ValueError for invalid values."""
    with pytest.raises(ValueError, match="Invalid ConfirmType: 'invalid'"):
        ConfirmType._missing_("invalid")

    with pytest.raises(ValueError, match="Invalid ConfirmType: 123"):
        ConfirmType._missing_(123)


def test_confirm_type_aliases():
    """Test if the _get_alias method returns correct aliases."""
    assert ConfirmType._get_alias("yes") == "yes_no"
    assert ConfirmType._get_alias("ok") == "ok_cancel"
    assert ConfirmType._get_alias("type") == "type_word"
    assert ConfirmType._get_alias("word") == "type_word"
    assert ConfirmType._get_alias("word_cancel") == "type_word_cancel"
    assert ConfirmType._get_alias("ack") == "acknowledge"


def test_confirm_type_missing_aliases():
    """Test if the _missing_ method handles aliases correctly."""
    assert ConfirmType("yes") == ConfirmType.YES_NO
    assert ConfirmType("ok") == ConfirmType.OK_CANCEL
    assert ConfirmType("word") == ConfirmType.TYPE_WORD
    assert ConfirmType("ack") == ConfirmType.ACKNOWLEDGE

    with pytest.raises(ValueError, match="Invalid ConfirmType: 'unknown'"):
        ConfirmType._missing_("unknown")


def test_selection_return_type_enum():
    """Test if the SelectionReturnType enum has all expected members."""
    assert SelectionReturnType.KEY.value == "key"
    assert SelectionReturnType.VALUE.value == "value"
    assert SelectionReturnType.DESCRIPTION.value == "description"
    assert SelectionReturnType.DESCRIPTION_VALUE.value == "description_value"
    assert SelectionReturnType.ITEMS.value == "items"

    assert str(SelectionReturnType.KEY) == "key"


def test_selection_return_type_choices():
    """Test if the SelectionReturnType choices method returns all enum members."""
    choices = SelectionReturnType.choices()
    assert len(choices) == 5
    assert all(isinstance(choice, SelectionReturnType) for choice in choices)


def test_selection_return_type_missing():
    """Test if the _missing_ method raises ValueError for invalid values."""
    with pytest.raises(ValueError, match="Invalid SelectionReturnType: 'invalid'"):
        SelectionReturnType._missing_("invalid")

    with pytest.raises(ValueError, match="Invalid SelectionReturnType: 123"):
        SelectionReturnType._missing_(123)


def test_selection_return_type_aliases():
    """Test if the _get_alias method returns correct aliases."""
    assert SelectionReturnType._get_alias("desc") == "description"
    assert SelectionReturnType._get_alias("desc_value") == "description_value"
    assert SelectionReturnType._get_alias("unknown") == "unknown"


def test_selection_return_type_missing_aliases():
    """Test if the _missing_ method handles aliases correctly."""
    assert SelectionReturnType._missing_("desc") == SelectionReturnType.DESCRIPTION
    assert (
        SelectionReturnType._missing_("desc_value")
        == SelectionReturnType.DESCRIPTION_VALUE
    )

    with pytest.raises(ValueError, match="Invalid SelectionReturnType: 'unknown'"):
        SelectionReturnType._missing_("unknown")
