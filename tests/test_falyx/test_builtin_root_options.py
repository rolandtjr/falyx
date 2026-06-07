import logging

from falyx import Falyx
from falyx.action import Action
from falyx.debug import log_after, log_before, log_error, log_success
from falyx.hook_manager import HookType


def test_apply_root_options_sets_falyx_logger_level_from_root_verbose():
    flx = Falyx()

    falyx_logger = logging.getLogger("falyx")
    original_level = falyx_logger.level
    try:
        flx.options_manager.set("verbose", True, "root")
        flx._apply_root_options()
        assert falyx_logger.level == logging.DEBUG

        flx.options_manager.set("verbose", False, "root")
        flx._apply_root_options()
        assert falyx_logger.level == logging.WARNING
    finally:
        falyx_logger.setLevel(original_level)


def test_apply_root_options_registers_debug_hooks_across_command_and_action_graph():
    action = Action("deploy-action", lambda: "ok")
    flx = Falyx()
    command = flx.add_command(
        key="D",
        description="Deploy",
        action=action,
    )

    assert flx.hooks._hooks[HookType.BEFORE] == []
    assert command.hooks._hooks[HookType.BEFORE] == []
    assert action.hooks._hooks[HookType.BEFORE] == []

    flx.options_manager.set("debug_hooks", True, "root")
    flx._apply_root_options()

    assert flx.hooks._hooks[HookType.BEFORE] == [log_before]
    assert flx.hooks._hooks[HookType.ON_SUCCESS] == [log_success]
    assert flx.hooks._hooks[HookType.ON_ERROR] == [log_error]
    assert flx.hooks._hooks[HookType.AFTER] == [log_after]

    assert command.hooks._hooks[HookType.BEFORE] == [log_before]
    assert command.hooks._hooks[HookType.ON_SUCCESS] == [log_success]
    assert command.hooks._hooks[HookType.ON_ERROR] == [log_error]
    assert command.hooks._hooks[HookType.AFTER] == [log_after]

    assert action.hooks._hooks[HookType.BEFORE] == [log_before]
    assert action.hooks._hooks[HookType.ON_SUCCESS] == [log_success]
    assert action.hooks._hooks[HookType.ON_ERROR] == [log_error]
    assert action.hooks._hooks[HookType.AFTER] == [log_after]
