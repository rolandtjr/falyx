# test_command.py
import pytest

from falyx.action import Action, BaseIOAction, ChainedAction
from falyx.command import Command
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
@pytest.mark.asyncio
async def test_command_creation():
    """Test if Command can be created with a callable."""
    action = Action("test_action", dummy_action)
    cmd = Command(key="TEST", description="Test Command", action=action)
    assert cmd.key == "TEST"
    assert cmd.description == "Test Command"
    assert cmd.action == action

    result = await cmd()
    assert result == "ok"
    assert cmd.result == "ok"


def test_command_str():
    """Test if Command string representation is correct."""
    action = Action("test_action", dummy_action)
    cmd = Command(key="TEST", description="Test Command", action=action)
    print(cmd)
    assert (
        str(cmd)
        == "Command(key='TEST', description='Test Command' action='Action(name='test_action', action=dummy_action, retry=False, rollback=False)')"
    )


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
        action=DummyInputAction(
            name="dummy_input_action",
        ),
        retry=True,
    )
    assert cmd.retry is True
    with pytest.raises(Exception) as exc_info:
        assert cmd.action.retry_policy.enabled is False
    assert "'DummyInputAction' object has no attribute 'retry_policy'" in str(
        exc_info.value
    )


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
        action=DummyInputAction(
            name="dummy_input_action",
        ),
        retry_all=True,
    )
    assert cmd.retry_all is True
    with pytest.raises(Exception) as exc_info:
        assert cmd.action.retry_policy.enabled is False
    assert "'DummyInputAction' object has no attribute 'retry_policy'" in str(
        exc_info.value
    )


@pytest.mark.asyncio
async def test_command_exception_handling():
    """Test if Command handles exceptions correctly."""

    async def bad_action():
        raise ZeroDivisionError("This is a test exception")

    cmd = Command(key="TEST", description="Test Command", action=bad_action)

    with pytest.raises(ZeroDivisionError):
        await cmd()

    assert cmd.result is None
    assert isinstance(cmd._context.exception, ZeroDivisionError)


def test_command_bad_action():
    """Test if Command raises an exception when action is not callable."""
    with pytest.raises(TypeError) as exc_info:
        Command(key="TEST", description="Test Command", action="not_callable")
    assert str(exc_info.value) == "Action must be a callable or an instance of BaseAction"
