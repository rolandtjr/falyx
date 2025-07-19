import pytest

from falyx.action import ConfirmAction


@pytest.mark.asyncio
async def test_confirm_action_yes_no():
    action = ConfirmAction(
        name="test",
        message="Are you sure?",
        never_prompt=True,
        confirm_type="yes_no",
    )

    result = await action()
    assert result is True


@pytest.mark.asyncio
async def test_confirm_action_yes_cancel():
    action = ConfirmAction(
        name="test",
        message="Are you sure?",
        never_prompt=True,
        confirm_type="yes_cancel",
    )

    result = await action()
    assert result is True


@pytest.mark.asyncio
async def test_confirm_action_yes_no_cancel():
    action = ConfirmAction(
        name="test",
        message="Are you sure?",
        never_prompt=True,
        confirm_type="yes_no_cancel",
    )

    result = await action()
    assert result is True


@pytest.mark.asyncio
async def test_confirm_action_type_word():
    action = ConfirmAction(
        name="test",
        message="Are you sure?",
        never_prompt=True,
        confirm_type="type_word",
    )

    result = await action()
    assert result is True


@pytest.mark.asyncio
async def test_confirm_action_type_word_cancel():
    action = ConfirmAction(
        name="test",
        message="Are you sure?",
        never_prompt=True,
        confirm_type="type_word_cancel",
    )

    result = await action()
    assert result is True


@pytest.mark.asyncio
async def test_confirm_action_ok_cancel():
    action = ConfirmAction(
        name="test",
        message="Are you sure?",
        never_prompt=True,
        confirm_type="ok_cancel",
    )

    result = await action()
    assert result is True


@pytest.mark.asyncio
async def test_confirm_action_acknowledge():
    action = ConfirmAction(
        name="test",
        message="Are you sure?",
        never_prompt=True,
        confirm_type="acknowledge",
    )

    result = await action()
    assert result is True
