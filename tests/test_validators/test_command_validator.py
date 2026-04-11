from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.validation import ValidationError

from falyx.routing import RouteKind
from falyx.validators import CommandValidator


@pytest.mark.asyncio
async def test_command_validator_validates_command():
    fake_falyx = AsyncMock()
    fake_route = SimpleNamespace()
    fake_route.is_preview = False
    fake_route.kind = RouteKind.NAMESPACE_HELP
    fake_falyx.prepare_route.return_value = (fake_route, (), {}, {})
    validator = CommandValidator(fake_falyx, "Invalid!")

    await validator.validate_async(Document("valid"))
    fake_falyx.prepare_route.assert_awaited_once()


@pytest.mark.asyncio
async def test_command_validator_rejects_invalid_command():
    fake_falyx = AsyncMock()
    fake_falyx.prepare_route.return_value = (None, (), {}, {})
    validator = CommandValidator(fake_falyx, "Invalid!")

    with pytest.raises(ValidationError):
        await validator.validate_async(Document(""))

    with pytest.raises(ValidationError):
        await validator.validate_async(Document("not_a_command"))


@pytest.mark.asyncio
async def test_command_validator_is_preview():
    fake_falyx = AsyncMock()
    fake_route = SimpleNamespace()
    fake_route.is_preview = True
    fake_falyx.prepare_route.return_value = (fake_route, (), {}, {})
    validator = CommandValidator(fake_falyx, "Invalid!")

    await validator.validate_async(Document("?preview_command"))
    fake_falyx.prepare_route.assert_awaited_once_with(
        "?preview_command", from_validate=True
    )
