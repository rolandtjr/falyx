import pytest

from falyx.action import ChainedAction
from falyx.exceptions import EmptyChainError

@pytest.mark.asyncio
async def test_chained_action_raises_empty_chain_error_when_no_actions():
    """A ChainedAction with no actions should raise an EmptyChainError immediately."""
    chain = ChainedAction(name="empty_chain", actions=[])

    with pytest.raises(EmptyChainError) as exc_info:
        await chain()

    assert "No actions to execute." in str(exc_info.value)
    assert "empty_chain" in str(exc_info.value)

@pytest.mark.asyncio
async def test_chained_action_raises_empty_chain_error_when_actions_are_none():
    """A ChainedAction with None as actions should raise an EmptyChainError immediately."""
    chain = ChainedAction(name="none_chain", actions=None)

    with pytest.raises(EmptyChainError) as exc_info:
        await chain()

    assert "No actions to execute." in str(exc_info.value)
    assert "none_chain" in str(exc_info.value)

