import pytest

from falyx.action import Action, ChainedAction, ActionGroup, FallbackAction
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.context import ExecutionContext

asyncio_default_fixture_loop_scope = "function"

# --- Helpers ---
async def capturing_hook(context: ExecutionContext):
    context.extra["hook_triggered"] = True

# --- Fixtures ---
@pytest.fixture
def hook_manager():
    hm = HookManager()
    hm.register(HookType.BEFORE, capturing_hook)
    return hm

@pytest.fixture(autouse=True)
def clean_registry():
    er.clear()
    yield
    er.clear()

def test_action_enable_retry():
    """Test if Action can be created with retry=True."""
    action = Action("test_action", lambda: "Hello, World!", retry=True)
    assert action.retry_policy.enabled is True