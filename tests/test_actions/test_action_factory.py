import pytest

from falyx.action import Action, ActionFactory, ChainedAction


def make_chain(value) -> ChainedAction:
    return ChainedAction(
        "test_chain",
        [
            Action("action1", lambda: value + "_1"),
            Action("action2", lambda: value + "_2"),
        ],
        return_list=True,
    )


@pytest.mark.asyncio
async def test_action_factory_action():
    action = ActionFactory(name="test_action", factory=make_chain, args=("test_value",))

    result = await action()

    assert result == ["test_value_1", "test_value_2"]
