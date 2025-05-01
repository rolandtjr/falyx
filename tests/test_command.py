# test_command.py
import pytest

from falyx.action import Action, ActionGroup, ChainedAction
from falyx.command import Command
from falyx.io_action import BaseIOAction
from falyx.execution_registry import ExecutionRegistry as er
from falyx.retry import RetryPolicy

asyncio_default_fixture_loop_scope = "function"

# --- Fixtures ---
@pytest.fixture(autouse=True)
def clean_registry():
    er.clear()
    yield
    er.clear()

# --- Dummy Action ---
async def dummy_action():
    return "ok"

# --- Dummy IO Action ---
class DummyInputAction(BaseIOAction):
    async def _run(self, *args, **kwargs):
        return "needs input"

    async def preview(self, parent=None):
        pass

# --- Tests ---
def test_command_creation():
    """Test if Command can be created with a callable."""
    action = Action("test_action", dummy_action)
    cmd = Command(
        key="TEST",
        description="Test Command",
        action=action
    )
    assert cmd.key == "TEST"
    assert cmd.description == "Test Command"
    assert cmd.action == action

def test_command_str():
    """Test if Command string representation is correct."""
    action = Action("test_action", dummy_action)
    cmd = Command(
        key="TEST",
        description="Test Command",
        action=action
    )
    print(cmd)
    assert str(cmd) == "Command(key='TEST', description='Test Command' action='Action(name='test_action', action=dummy_action, args=(), kwargs={}, retry=False)')"

@pytest.mark.parametrize(
    "action_factory, expected_requires_input",
    [
        (lambda: Action(name="normal", action=dummy_action), False),
        (lambda: DummyInputAction(name="io"), True),
        (lambda: ChainedAction(name="chain", actions=[DummyInputAction(name="io")]), True),
        (lambda: ActionGroup(name="group", actions=[DummyInputAction(name="io")]), True),
    ]
)
def test_command_requires_input_detection(action_factory, expected_requires_input):
    action = action_factory()
    cmd = Command(
        key="TEST",
        description="Test Command",
        action=action
    )

    assert cmd.requires_input == expected_requires_input
    if expected_requires_input:
        assert cmd.hidden is True
    else:
        assert cmd.hidden is False

def test_requires_input_flag_detected_for_baseioaction():
    """Command should automatically detect requires_input=True for BaseIOAction."""
    cmd = Command(
        key="X",
        description="Echo input",
        action=DummyInputAction(name="dummy"),
    )
    assert cmd.requires_input is True
    assert cmd.hidden is True

def test_requires_input_manual_override():
    """Command manually set requires_input=False should not auto-hide."""
    cmd = Command(
        key="Y",
        description="Custom input command",
        action=DummyInputAction(name="dummy"),
        requires_input=False,
    )
    assert cmd.requires_input is False
    assert cmd.hidden is False

def test_default_command_does_not_require_input():
    """Normal Command without IO Action should not require input."""
    cmd = Command(
        key="Z",
        description="Simple action",
        action=lambda: 42,
    )
    assert cmd.requires_input is False
    assert cmd.hidden is False

def test_chain_requires_input():
    """If first action in a chain requires input, the command should require input."""
    chain = ChainedAction(
        name="ChainWithInput",
        actions=[
            DummyInputAction(name="dummy"),
            Action(name="action1", action=lambda: 1),
        ],
    )
    cmd = Command(
        key="A",
        description="Chain with input",
        action=chain,
    )
    assert cmd.requires_input is True
    assert cmd.hidden is True

def test_group_requires_input():
    """If any action in a group requires input, the command should require input."""
    group = ActionGroup(
        name="GroupWithInput",
        actions=[
            Action(name="action1", action=lambda: 1),
            DummyInputAction(name="dummy"),
        ],
    )
    cmd = Command(
        key="B",
        description="Group with input",
        action=group,
    )
    assert cmd.requires_input is True
    assert cmd.hidden is True


def test_enable_retry():
    """Command should enable retry if action is an Action and  retry is set to True."""
    cmd = Command(
        key="A",
        description="Retry action",
        action=Action(
            name="retry_action",
            action=lambda: 42,
        ),
        retry=True,
    )
    assert cmd.retry is True
    assert cmd.action.retry_policy.enabled is True

def test_enable_retry_with_retry_policy():
    """Command should enable retry if action is an Action and retry_policy is set."""
    retry_policy = RetryPolicy(
        max_retries=3,
        delay=1,
        backoff=2,
        enabled=True,
    )
    cmd = Command(
        key="B",
        description="Retry action with policy",
        action=Action(
            name="retry_action_with_policy",
            action=lambda: 42,
        ),
        retry_policy=retry_policy,
    )
    assert cmd.action.retry_policy.enabled is True
    assert cmd.action.retry_policy == retry_policy

def test_enable_retry_not_action():
    """Command should not enable retry if action is not an Action."""
    cmd = Command(
        key="C",
        description="Retry action",
        action=DummyInputAction,
        retry=True,
    )
    assert cmd.retry is True
    with pytest.raises(Exception) as exc_info:
        assert cmd.action.retry_policy.enabled is False
    assert "'function' object has no attribute 'retry_policy'" in str(exc_info.value)

def test_chain_retry_all():
    """retry_all should retry all Actions inside a ChainedAction recursively."""
    chain = ChainedAction(
        name="ChainWithRetry",
        actions=[
            Action(name="action1", action=lambda: 1),
            Action(name="action2", action=lambda: 2),
        ],
    )
    cmd = Command(
        key="D",
        description="Chain with retry",
        action=chain,
        retry_all=True,
    )

    assert cmd.retry_all is True
    assert cmd.retry_policy.enabled is True
    assert chain.actions[0].retry_policy.enabled is True
    assert chain.actions[1].retry_policy.enabled is True

def test_chain_retry_all_not_base_action():
    """retry_all should not be set if action is not a ChainedAction."""
    cmd = Command(
        key="E",
        description="Chain with retry",
        action=DummyInputAction,
        retry_all=True,
    )
    assert cmd.retry_all is True
    with pytest.raises(Exception) as exc_info:
        assert cmd.action.retry_policy.enabled is False
    assert "'function' object has no attribute 'retry_policy'" in str(exc_info.value)

