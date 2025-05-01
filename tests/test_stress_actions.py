import pytest
import asyncio
from falyx.action import Action, ChainedAction, ActionGroup, FallbackAction
from falyx.execution_registry import ExecutionRegistry as er
from falyx.hook_manager import HookType
from falyx.context import ExecutionContext

# --- Fixtures ---


@pytest.fixture(autouse=True)
def clean_registry():
    er.clear()
    yield
    er.clear()


# --- Stress Tests ---


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

    assert "fail_action" in str(exc_info.value)


@pytest.mark.asyncio
async def test_chained_action_with_nested_group():
    group = ActionGroup(
        name="nested_group",
        actions=[
            Action(
                name="g1",
                action=lambda last_result: f"{last_result} + 10",
                inject_last_result=True,
            ),
            Action(
                name="g2",
                action=lambda last_result: f"{last_result} + 20",
                inject_last_result=True,
            ),
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
    assert result[0] == "start"
    result_dict = dict(result[1])
    assert result_dict == {"g1": "start + 10", "g2": "start + 20"}


@pytest.mark.asyncio
async def test_chained_action_with_error_mid_fallback():
    async def ok():
        return 1

    async def fail():
        raise RuntimeError("bad")

    chain = ChainedAction(
        name="group_with_fallback",
        actions=[
            Action(name="ok", action=ok),
            Action(name="fail", action=fail),
            FallbackAction(fallback="recovered"),
        ],
        return_list=True,
    )

    result = await chain()
    assert result == [1, None, "recovered"]


@pytest.mark.asyncio
async def test_chained_action_double_fallback():
    async def fetch_data():
        return None

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
            FallbackAction(fallback="default2"),
            Action(name="Enrich", action=enrich),
        ],
        auto_inject=True,
        return_list=True,
    )

    result = await chain()
    assert result == [None, "default1", "default1", "default1", "Enriched: default1"]


@pytest.mark.asyncio
async def test_large_chain_stress():
    chain = ChainedAction(
        name="large_chain",
        actions=[
            Action(
                name=f"a{i}",
                action=lambda last_result: (
                    last_result + 1 if last_result is not None else 0
                ),
                inject_last_result=True,
            )
            for i in range(50)
        ],
        auto_inject=True,
    )

    result = await chain()
    assert result == 49  # Start from 0 and add 1 fifty times


@pytest.mark.asyncio
async def test_nested_chain_inside_group():
    inner_chain = ChainedAction(
        name="inner",
        actions=[
            1,
            Action(
                name="a",
                action=lambda last_result: last_result + 1,
                inject_last_result=True,
            ),
            Action(
                name="b",
                action=lambda last_result: last_result + 2,
                inject_last_result=True,
            ),
        ],
    )

    group = ActionGroup(
        name="outer_group",
        actions=[
            Action(name="starter", action=lambda: 10),
            inner_chain,
        ],
    )

    result = await group()
    result_dict = dict(result)
    assert result_dict["starter"] == 10
    assert result_dict["inner"] == 4


@pytest.mark.asyncio
async def test_mixed_sync_async_actions():
    async def async_action(last_result):
        return last_result + 5

    def sync_action(last_result):
        return last_result * 2

    chain = ChainedAction(
        name="mixed_chain",
        actions=[
            Action(name="start", action=lambda: 1),
            Action(name="double", action=sync_action, inject_last_result=True),
            Action(name="plus_five", action=async_action, inject_last_result=True),
        ],
    )

    result = await chain()
    assert result == 7
