from unittest.mock import AsyncMock

import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.validators import CommandValidator


@pytest.mark.asyncio
async def test_command_validator_validates_command():
    fake_falyx = AsyncMock()
    fake_falyx.get_command.return_value = (False, object(), (), {})
    validator = CommandValidator(fake_falyx, "Invalid!")

    await validator.validate_async(Document("valid"))
    fake_falyx.get_command.assert_awaited_once()


@pytest.mark.asyncio
async def test_command_validator_rejects_invalid_command():
    fake_falyx = AsyncMock()
    fake_falyx.get_command.return_value = (False, None, (), {})
    validator = CommandValidator(fake_falyx, "Invalid!")

    with pytest.raises(ValidationError):
        await validator.validate_async(Document("not_a_command"))

    with pytest.raises(ValidationError):
        await validator.validate_async(Document(""))


@pytest.mark.asyncio
async def test_command_validator_is_preview():
    fake_falyx = AsyncMock()
    fake_falyx.get_command.return_value = (True, None, (), {})
    validator = CommandValidator(fake_falyx, "Invalid!")

    await validator.validate_async(Document("?preview_command"))
    fake_falyx.get_command.assert_awaited_once_with(
        "?preview_command", from_validate=True
    )
