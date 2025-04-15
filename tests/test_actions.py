import pytest
import asyncio
import pickle
import warnings
from falyx.action import Action, ChainedAction, ActionGroup, ProcessAction
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType
from falyx.context import ExecutionContext, ResultsContext

asyncio_default_fixture_loop_scope = "function"

# --- Helpers ---

async def dummy_action(x: int = 0) -> int:
    return x + 1

async def capturing_hook(context: ExecutionContext):
    context.extra["hook_triggered"] = True

# --- Fixtures ---

@pytest.fixture
def sample_action():
    return Action(name="increment", action=dummy_action, kwargs={"x": 5})

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

# --- Tests ---

@pytest.mark.asyncio
async def test_action_runs_correctly(sample_action):
    result = await sample_action()
    assert result == 6

@pytest.mark.asyncio
async def test_action_hook_lifecycle(hook_manager):
    action = Action(
        name="hooked",
        action=lambda: 42,
        hooks=hook_manager
    )

    await action()

    context = er.get_latest()
    assert context.name == "hooked"
    assert context.extra.get("hook_triggered") is True

@pytest.mark.asyncio
async def test_chained_action_with_result_injection():
    actions = [
        Action(name="start", action=lambda: 1),
        Action(name="add_last", action=lambda last_result: last_result + 5, inject_last_result=True),
        Action(name="multiply", action=lambda last_result: last_result * 2, inject_last_result=True)
    ]
    chain = ChainedAction(name="test_chain", actions=actions, inject_last_result=True)
    result = await chain()
    assert result == [1, 6, 12]

@pytest.mark.asyncio
async def test_action_group_runs_in_parallel():
    actions = [
        Action(name="a", action=lambda: 1),
        Action(name="b", action=lambda: 2),
        Action(name="c", action=lambda: 3),
    ]
    group = ActionGroup(name="parallel", actions=actions)
    result = await group()
    result_dict = dict(result)
    assert result_dict == {"a": 1, "b": 2, "c": 3}

@pytest.mark.asyncio
async def test_chained_action_inject_from_action():
    inner_chain = ChainedAction(
        name="inner_chain",
        actions=[
            Action(name="inner_first", action=lambda last_result: last_result + 10, inject_last_result=True),
            Action(name="inner_second", action=lambda last_result: last_result + 5, inject_last_result=True),
        ]
    )
    actions = [
        Action(name="first", action=lambda: 1),
        Action(name="second", action=lambda last_result: last_result + 2, inject_last_result=True),
        inner_chain,

    ]
    outer_chain = ChainedAction(name="test_chain", actions=actions)
    result = await outer_chain()
    assert result == [1, 3, [13, 18]]

@pytest.mark.asyncio
async def test_chained_action_with_group():
    group = ActionGroup(
        name="group",
        actions=[
            Action(name="a", action=lambda last_result: last_result + 1, inject_last_result=True),
            Action(name="b", action=lambda last_result: last_result + 2, inject_last_result=True),
            Action(name="c", action=lambda: 3),
        ]
    )
    actions = [
        Action(name="first", action=lambda: 1),
        Action(name="second", action=lambda last_result: last_result + 2, inject_last_result=True),
        group,
    ]
    chain = ChainedAction(name="test_chain", actions=actions)
    result = await chain()
    assert result == [1, 3, [("a", 4), ("b", 5), ("c", 3)]]

@pytest.mark.asyncio
async def test_action_error_triggers_error_hook():
    def fail():
        raise ValueError("boom")

    hooks = HookManager()
    flag = {}

    async def error_hook(ctx):
        flag["called"] = True

    hooks.register(HookType.ON_ERROR, error_hook)
    action = Action(name="fail_action", action=fail, hooks=hooks)

    with pytest.raises(ValueError):
        await action()

    assert flag.get("called") is True

@pytest.mark.asyncio
async def test_chained_action_rollback_on_failure():
    rollback_called = []

    async def success():
        return "ok"

    async def fail():
        raise RuntimeError("fail")

    async def rollback_fn():
        rollback_called.append("rolled back")

    actions = [
        Action(name="ok", action=success, rollback=rollback_fn),
        Action(name="fail", action=fail, rollback=rollback_fn)
    ]

    chain = ChainedAction(name="chain", actions=actions)

    with pytest.raises(RuntimeError):
        await chain()

    assert rollback_called == ["rolled back"]

def slow_add(x, y):
    return x + y

@pytest.mark.asyncio
async def test_process_action_executes_correctly():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        action = ProcessAction(name="proc", func=slow_add, args=(2, 3))
        result = await action()
        assert result == 5

unpickleable = lambda x: x + 1

@pytest.mark.asyncio
async def test_process_action_rejects_unpickleable():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        action = ProcessAction(name="proc_fail", func=unpickleable, args=(2,))
        with pytest.raises(pickle.PicklingError, match="Can't pickle"):
            await action()

@pytest.mark.asyncio
async def test_register_hooks_recursively_propagates():
    hook = lambda ctx: ctx.extra.update({"test_marker": True})

    chain = ChainedAction(name="chain", actions=[
        Action(name="a", action=lambda: 1),
        Action(name="b", action=lambda: 2),
    ])
    chain.register_hooks_recursively(HookType.BEFORE, hook)

    await chain()

    for ctx in er.get_by_name("a") + er.get_by_name("b"):
        assert ctx.extra.get("test_marker") is True

@pytest.mark.asyncio
async def test_action_hook_recovers_error():
    async def flaky():
        raise ValueError("fail")

    async def recovery_hook(ctx):
        ctx.result = 99
        ctx.exception = None

    hooks = HookManager()
    hooks.register(HookType.ON_ERROR, recovery_hook)
    action = Action(name="recovering", action=flaky, hooks=hooks)

    result = await action()
    assert result == 99

@pytest.mark.asyncio
async def test_action_group_injects_last_result():
    group = ActionGroup(name="group", actions=[
        Action(name="g1", action=lambda last_result: last_result + 10, inject_last_result=True),
        Action(name="g2", action=lambda last_result: last_result + 20, inject_last_result=True),
    ])
    chain = ChainedAction(name="with_group", actions=[
        Action(name="first", action=lambda: 5),
        group,
    ])
    result = await chain()
    result_dict = dict(result[1])
    assert result_dict == {"g1": 15, "g2": 25}
