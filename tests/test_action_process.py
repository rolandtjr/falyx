import pickle
import warnings

import pytest

from falyx.action import ProcessAction
from falyx.execution_registry import ExecutionRegistry as er

# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_registry():
    er.clear()
    yield
    er.clear()


def slow_add(x, y):
    return x + y


# --- Tests ---


@pytest.mark.asyncio
async def test_process_action_executes_correctly():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        action = ProcessAction(name="proc", action=slow_add, args=(2, 3))
        result = await action()
        assert result == 5


unpickleable = lambda x: x + 1  # noqa: E731


@pytest.mark.asyncio
async def test_process_action_rejects_unpickleable():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        action = ProcessAction(name="proc_fail", action=unpickleable, args=(2,))
        with pytest.raises(pickle.PicklingError, match="Can't pickle"):
            await action()
