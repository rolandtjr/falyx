import pytest
from rich.text import Text

from falyx.action import LoadFileAction
from falyx.console import console as falyx_console


@pytest.mark.asyncio
async def test_load_json_file_action(tmp_path):
    mock_data = '{"key": "value"}'
    file = tmp_path / "test.json"
    file.write_text(mock_data)
    action = LoadFileAction(name="load-file", file_path=file, file_type="json")
    result = await action()
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_load_yaml_file_action(tmp_path):
    mock_data = "key: value"
    file = tmp_path / "test.yaml"
    file.write_text(mock_data)
    action = LoadFileAction(name="load-file", file_path=file, file_type="yaml")
    result = await action()
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_load_toml_file_action(tmp_path):
    mock_data = 'key = "value"'
    file = tmp_path / "test.toml"
    file.write_text(mock_data)
    action = LoadFileAction(name="load-file", file_path=file, file_type="toml")
    result = await action()
    assert result == {"key": "value"}


@pytest.mark.asyncio
async def test_load_csv_file_action(tmp_path):
    mock_data = "key,value\nfoo,bar"
    file = tmp_path / "test.csv"
    file.write_text(mock_data)
    action = LoadFileAction(name="load-file", file_path=file, file_type="csv")
    result = await action()
    print(result)
    assert result == [["key", "value"], ["foo", "bar"]]


@pytest.mark.asyncio
async def test_load_tsv_file_action(tmp_path):
    mock_data = "key\tvalue\nfoo\tbar"
    file = tmp_path / "test.tsv"
    file.write_text(mock_data)
    action = LoadFileAction(name="load-file", file_path=file, file_type="tsv")
    result = await action()
    assert result == [["key", "value"], ["foo", "bar"]]


@pytest.mark.asyncio
async def test_load_file_action_invalid_path():
    action = LoadFileAction(
        name="load-file", file_path="non_existent_file.json", file_type="json"
    )
    with pytest.raises(FileNotFoundError):
        await action()


@pytest.mark.asyncio
async def test_load_file_action_invalid_json(tmp_path):
    invalid_json = '{"key": "value"'  # Missing closing brace
    file = tmp_path / "invalid.json"
    file.write_text(invalid_json)
    action = LoadFileAction(name="load-file", file_path=file, file_type="json")
    with pytest.raises(ValueError):
        await action()


@pytest.mark.asyncio
async def test_load_file_action_unsupported_type(tmp_path):
    file = tmp_path / "test.txt"
    file.write_text("Just some text")
    with pytest.raises(ValueError):
        LoadFileAction(name="load-file", file_path=file, file_type="unsupported")


@pytest.mark.asyncio
async def test_preview_of_load_file_action(tmp_path):
    mock_data = '{"key": "value"}'
    file = tmp_path / "test.json"
    file.write_text(mock_data)
    action = LoadFileAction(name="load-file", file_path=file, file_type="json")
    with falyx_console.capture() as capture:
        await action.preview()
    captured = Text.from_ansi(capture.get()).plain
    assert "LoadFileAction" in captured
    assert "test.json" in captured
    assert "load-file" in captured
    assert "JSON" in captured
    assert "key" in captured
    assert "value" in captured
