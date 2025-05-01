import pytest

from falyx.action import Action, ChainedAction
from falyx.execution_registry import ExecutionRegistry as er
from falyx.retry_utils import enable_retries_recursively

asyncio_default_fixture_loop_scope = "function"

# --- Fixtures ---
@pytest.fixture(autouse=True)
def clean_registry():
    er.clear()
    yield
    er.clear()

def test_action_enable_retry():
    """Test if Action can be created with retry=True."""
    action = Action("test_action", lambda: "Hello, World!", retry=True)
    assert action.retry_policy.enabled is True


@pytest.mark.asyncio
async def test_enable_retries_recursively():
    """Test if Action can be created with retry=True."""
    action = Action("test_action", lambda: "Hello, World!")
    assert action.retry_policy.enabled is False

    chained_action = ChainedAction(
        name="Chained Action",
        actions=[action],
    )

    enable_retries_recursively(chained_action, policy=None)
    assert action.retry_policy.enabled is True
