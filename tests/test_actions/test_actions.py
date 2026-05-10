import pytest

from falyx.action import Action, ActionGroup, ChainedAction, FallbackAction
from falyx.context import ExecutionContext
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookManager, HookType

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


# --- Tests ---


@pytest.mark.asyncio
async def test_action_runs_correctly():
    async def dummy_action(x: int = 0) -> int:
        return x + 1

    sample_action = Action(name="increment", action=dummy_action, kwargs={"x": 5})
    result = await sample_action()
    assert result == 6


@pytest.mark.asyncio
async def test_action_hook_lifecycle(hook_manager):
    async def a1():
        return 42

    action = Action(name="hooked", action=a1, hooks=hook_manager)

    await action()

    context = er.get_latest()
    assert context.name == "hooked"
    assert context.extra.get("hook_triggered") is True


@pytest.mark.asyncio
async def test_chained_action_with_result_injection():
    async def a1():
        return 1

    async def a2(last_result):
        return last_result + 5

    async def a3(last_result):
        return last_result * 2

    actions = [
        Action(name="start", action=a1),
        Action(name="add_last", action=a2, inject_last_result=True),
        Action(name="multiply", action=a3, inject_last_result=True),
    ]
    chain = ChainedAction(
        name="test_chain", actions=actions, inject_last_result=True, return_list=True
    )
    result = await chain()
    assert result == [1, 6, 12]
    chain = ChainedAction(name="test_chain", actions=actions, inject_last_result=True)
    result = await chain()
    assert result == 12


@pytest.mark.asyncio
async def test_action_group_runs_in_parallel():
    async def a1():
        return 1

    async def a2():
        return 2

    async def a3():
        return 3

    actions = [
        Action(name="a", action=a1),
        Action(name="b", action=a2),
        Action(name="c", action=a3),
    ]
    group = ActionGroup(name="parallel", actions=actions)
    result = await group()
    result_dict = dict(result)
    assert result_dict == {"a": 1, "b": 2, "c": 3}


@pytest.mark.asyncio
async def test_chained_action_inject_from_action():
    async def a1(last_result):
        return last_result + 10

    async def a2(last_result):
        return last_result + 5

    inner_chain = ChainedAction(
        name="inner_chain",
        actions=[
            Action(name="inner_first", action=a1, inject_last_result=True),
            Action(name="inner_second", action=a2, inject_last_result=True),
        ],
        return_list=True,
    )

    async def a3():
        return 1

    async def a4(last_result):
        return last_result + 2

    actions = [
        Action(name="first", action=a3),
        Action(name="second", action=a4, inject_last_result=True),
        inner_chain,
    ]
    outer_chain = ChainedAction(name="test_chain", actions=actions, return_list=True)
    result = await outer_chain()
    assert result == [1, 3, [13, 18]]


@pytest.mark.asyncio
async def test_chained_action_with_group():
    async def a1(last_result):
        return last_result + 1

    async def a2(last_result):
        return last_result + 2

    async def a3():
        return 3

    group = ActionGroup(
        name="group",
        actions=[
            Action(name="a", action=a1, inject_last_result=True),
            Action(name="b", action=a2, inject_last_result=True),
            Action(name="c", action=a3),
        ],
    )

    async def a4():
        return 1

    async def a5(last_result):
        return last_result + 2

    actions = [
        Action(name="first", action=a4),
        Action(name="second", action=a5, inject_last_result=True),
        group,
    ]
    chain = ChainedAction(name="test_chain", actions=actions, return_list=True)
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
        Action(name="fail", action=fail, rollback=rollback_fn),
    ]

    chain = ChainedAction(name="chain", actions=actions)

    with pytest.raises(RuntimeError):
        await chain()

    assert rollback_called == ["rolled back"]


@pytest.mark.asyncio
async def test_register_hooks_recursively_propagates():
    def hook(context):
        context.extra.update({"test_marker": True})

    async def a1():
        return 1

    async def a2():
        return 2

    chain = ChainedAction(
        name="chain",
        actions=[
            Action(name="a", action=a1),
            Action(name="b", action=a2),
        ],
    )
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
    async def a1(last_result):
        return last_result + 10

    async def a2(last_result):
        return last_result + 20

    group = ActionGroup(
        name="group",
        actions=[
            Action(name="g1", action=a1, inject_last_result=True),
            Action(name="g2", action=a2, inject_last_result=True),
        ],
    )

    async def a3():
        return 5

    chain = ChainedAction(
        name="with_group",
        actions=[
            Action(name="first", action=a3),
            group,
        ],
        return_list=True,
    )
    result = await chain()
    result_dict = dict(result[1])
    assert result_dict == {"g1": 15, "g2": 25}


@pytest.mark.asyncio
async def test_action_inject_last_result():
    async def a1():
        return 1

    async def a2(last_result):
        return last_result + 1

    a1 = Action(name="a1", action=a1)
    a2 = Action(name="a2", action=a2, inject_last_result=True)
    chain = ChainedAction(name="chain", actions=[a1, a2])
    result = await chain()
    assert result == 2


@pytest.mark.asyncio
async def test_action_inject_last_result_fail():
    async def a1():
        return 1

    async def a2(last_result):
        return last_result + 1

    a1 = Action(name="a1", action=a1)
    a2 = Action(name="a2", action=a2)
    chain = ChainedAction(name="chain", actions=[a1, a2])

    with pytest.raises(TypeError) as exc_info:
        await chain()

    assert "last_result" in str(exc_info.value)


@pytest.mark.asyncio
async def test_chained_action_auto_inject():
    async def a1():
        return 1

    async def a2(last_result):
        return last_result + 2

    a1 = Action(name="a1", action=a1)
    a2 = Action(name="a2", action=a2)
    chain = ChainedAction(
        name="chain", actions=[a1, a2], auto_inject=True, return_list=True
    )
    result = await chain()
    assert result == [1, 3]  # a2 receives last_result=1


@pytest.mark.asyncio
async def test_chained_action_no_auto_inject():
    async def a1():
        return 1

    async def a2():
        return 2

    a1 = Action(name="a1", action=a1)
    a2 = Action(name="a2", action=a2)
    chain = ChainedAction(
        name="no_inject", actions=[a1, a2], auto_inject=False, return_list=True
    )
    result = await chain()
    assert result == [1, 2]  # a2 does not receive 1


@pytest.mark.asyncio
async def test_chained_action_auto_inject_after_first():
    async def a1():
        return 1

    async def a2(last_result):
        return last_result + 1

    a1 = Action(name="a1", action=a1)
    a2 = Action(name="a2", action=a2)
    chain = ChainedAction(name="auto_inject", actions=[a1, a2], auto_inject=True)
    result = await chain()
    assert result == 2  # a2 receives last_result=1


@pytest.mark.asyncio
async def test_chained_action_with_literal_input():
    async def a1(last_result):
        return last_result + " world"

    a1 = Action(name="a1", action=a1)
    chain = ChainedAction(name="literal_inject", actions=["hello", a1], auto_inject=True)
    result = await chain()
    assert result == "hello world"  # "hello" is injected as last_result


@pytest.mark.asyncio
async def test_chained_action_manual_inject_override():
    async def a1():
        return 10

    async def a2(last_result):
        return last_result * 2

    a1 = Action(name="a1", action=a1)
    a2 = Action(name="a2", action=a2, inject_last_result=True)
    chain = ChainedAction(name="manual_override", actions=[a1, a2], auto_inject=False)
    result = await chain()
    assert result == 20  # Even without auto_inject, a2 still gets last_result


@pytest.mark.asyncio
async def test_chained_action_with_mid_literal():
    async def fetch_data():
        # Imagine this is some dynamic API call
        return None  # Simulate failure or missing data

    async def validate_data(last_result):
        if last_result is None:
            raise ValueError("Missing data!")
        return last_result

    async def enrich_data(last_result):
        return f"Enriched: {last_result}"

    chain = ChainedAction(
        name="fallback_pipeline",
        actions=[
            Action(name="FetchData", action=fetch_data),
            "default_value",  # <-- literal fallback injected mid-chain
            Action(name="ValidateData", action=validate_data),
            Action(name="EnrichData", action=enrich_data),
        ],
        auto_inject=True,
        return_list=True,
    )

    result = await chain()
    assert result == [None, "default_value", "default_value", "Enriched: default_value"]


@pytest.mark.asyncio
async def test_chained_action_with_mid_fallback():
    async def fetch_data():
        # Imagine this is some dynamic API call
        return None  # Simulate failure or missing data

    async def validate_data(last_result):
        if last_result is None:
            raise ValueError("Missing data!")
        return last_result

    async def enrich_data(last_result):
        return f"Enriched: {last_result}"

    chain = ChainedAction(
        name="fallback_pipeline",
        actions=[
            Action(name="FetchData", action=fetch_data),
            FallbackAction(fallback="default_value"),
            Action(name="ValidateData", action=validate_data),
            Action(name="EnrichData", action=enrich_data),
        ],
        auto_inject=True,
        return_list=True,
    )

    result = await chain()
    assert result == [None, "default_value", "default_value", "Enriched: default_value"]


@pytest.mark.asyncio
async def test_chained_action_with_success_mid_fallback():
    async def fetch_data():
        # Imagine this is some dynamic API call
        return "Result"  # Simulate success

    async def validate_data(last_result):
        if last_result is None:
            raise ValueError("Missing data!")
        return last_result

    async def enrich_data(last_result):
        return f"Enriched: {last_result}"

    chain = ChainedAction(
        name="fallback_pipeline",
        actions=[
            Action(name="FetchData", action=fetch_data),
            FallbackAction(fallback="default_value"),
            Action(name="ValidateData", action=validate_data),
            Action(name="EnrichData", action=enrich_data),
        ],
        auto_inject=True,
        return_list=True,
    )

    result = await chain()
    assert result == ["Result", "Result", "Result", "Enriched: Result"]


@pytest.mark.asyncio
async def test_action_group_partial_failure():
    async def succeed():
        return "ok"

    async def fail():
        raise ValueError("oops")

    group = ActionGroup(
        name="partial_group",
        actions=[
            Action(name="succeed_action", action=succeed),
            Action(name="fail_action", action=fail),
        ],
    )

    with pytest.raises(Exception) as exc_info:
        await group()

    assert er.get_by_name("succeed_action")[0].result == "ok"
    assert er.get_by_name("fail_action")[0].exception is not None
    assert "fail_action" in str(exc_info.value)


@pytest.mark.asyncio
async def test_chained_action_with_nested_group():
    async def g1(last_result):
        return last_result + "10"

    async def g2(last_result):
        return last_result + "20"

    group = ActionGroup(
        name="nested_group",
        actions=[
            Action(name="g1", action=g1, inject_last_result=True),
            Action(name="g2", action=g2, inject_last_result=True),
        ],
    )

    chain = ChainedAction(
        name="chain_with_group",
        actions=[
            "start",
            group,
        ],
        auto_inject=True,
        return_list=True,
    )

    result = await chain()
    # "start" -> group both receive "start" as last_result
    assert result[0] == "start"
    assert dict(result[1]) == {
        "g1": "start10",
        "g2": "start20",
    }  # Assuming string concatenation for example


@pytest.mark.asyncio
async def test_chained_action_double_fallback():
    async def fetch_data(last_result=None):
        raise ValueError("No data!")  # Simulate failure

    async def validate_data(last_result):
        if last_result is None:
            raise ValueError("No data!")
        return last_result

    async def enrich(last_result):
        return f"Enriched: {last_result}"

    chain = ChainedAction(
        name="fallback_chain",
        actions=[
            Action(name="Fetch", action=fetch_data),
            FallbackAction(fallback="default1"),
            Action(name="Validate", action=validate_data),
            Action(name="Fetch", action=fetch_data),
            FallbackAction(fallback="default2"),
            Action(name="Enrich", action=enrich),
        ],
        auto_inject=True,
        return_list=True,
    )

    result = await chain()
    assert result == [
        None,
        "default1",
        "default1",
        None,
        "default2",
        "Enriched: default2",
    ]
