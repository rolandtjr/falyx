from falyx.parser import ArgumentAction


def test_argument_action():
    action = ArgumentAction.APPEND
    assert action == ArgumentAction.APPEND
    assert action != ArgumentAction.STORE
    assert action != "invalid_action"
    assert action.value == "append"
    assert str(action) == "append"
    assert len(ArgumentAction.choices()) == 8
