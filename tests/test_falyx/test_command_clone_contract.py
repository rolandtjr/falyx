import pytest

from falyx import Falyx
from falyx.action import Action, ChainedAction
from falyx.command import Command
from falyx.options_manager import OptionsManager
from falyx.parser import CommandArgumentParser


def test_add_command_from_command_returns_bound_clone():
    source = Falyx(program="source")
    target = Falyx(program="target")

    original = source.add_command(
        "D",
        "Deploy",
        action=lambda: "ok",
        aliases=["deploy"],
        help_text="Deploy something.",
    )

    bound = target.add_command_from_command(original)

    assert bound is target.commands["D"]
    assert bound is not original
    assert bound.key == original.key
    assert bound.description == original.description
    assert bound.aliases == original.aliases
    assert bound.program == target.program


def test_add_command_from_command_does_not_reuse_original_options_manager():
    source = Falyx(program="source")
    target = Falyx(program="target")

    original = source.add_command("D", "Deploy", action=lambda: "ok")
    bound = target.add_command_from_command(original)

    assert original.options_manager is source.options_manager
    assert bound.options_manager is target.options_manager
    assert bound.options_manager is not original.options_manager


def test_add_command_from_command_returns_isolated_clone():
    flx1 = Falyx(program="one")
    flx2 = Falyx(program="two")

    original = flx1.add_command("D", "Deploy", action=Action("deploy", lambda: "ok"))
    bound = flx2.add_command_from_command(original)

    assert bound is not original
    assert bound.options_manager is flx2.options_manager
    assert original.options_manager is flx1.options_manager

    if bound.arg_parser and original.arg_parser:
        assert bound.arg_parser is not original.arg_parser
        assert bound.arg_parser.options_manager is flx2.options_manager
        assert original.arg_parser.options_manager is flx1.options_manager

    assert bound.action is not original.action


def test_clone_with_overrides_clones_arg_parser_and_base_action_graph():
    original_options = OptionsManager()
    cloned_options = OptionsManager()

    parser = CommandArgumentParser(
        command_key="D",
        command_description="Deploy",
        options_manager=original_options,
    )
    parser.add_argument("--region", default="us-east")

    action = ChainedAction(
        name="deploy-flow",
        actions=[
            Action("step-one", lambda: "one"),
            Action("step-two", lambda: "two"),
        ],
    )

    command = Command.build(
        key="D",
        description="Deploy",
        action=action,
        arg_parser=parser,
        options_manager=original_options,
        program="source",
    )

    cloned = command.clone_with_overrides(
        options_manager=cloned_options,
        program="target",
    )

    assert cloned is not command
    assert cloned.program == "target"
    assert cloned.options_manager is cloned_options
    assert command.options_manager is original_options

    assert cloned.arg_parser is not command.arg_parser
    assert cloned.arg_parser.options_manager is cloned_options
    assert command.arg_parser.options_manager is original_options

    assert cloned.action is not command.action
    assert isinstance(cloned.action, ChainedAction)
    assert isinstance(command.action, ChainedAction)

    assert cloned.action.actions is not command.action.actions
    assert len(cloned.action.actions) == len(command.action.actions)

    for cloned_child, original_child in zip(
        cloned.action.actions,
        command.action.actions,
        strict=True,
    ):
        assert cloned_child is not original_child
        assert cloned_child.name == original_child.name

    cloned.arg_parser.add_argument("--profile", default="dev")
    assert command.arg_parser.get_argument("profile") is None


def test_clone_with_overrides_preserves_boolean_contract_flags():
    command = Command.build(
        "H",
        "Hidden-ish helper",
        lambda: None,
        auto_args=False,
        simple_help_signature=True,
        ignore_in_history=True,
    )

    cloned = command.clone_with_overrides()

    assert cloned.auto_args is False
    assert cloned.simple_help_signature is True
    assert cloned.ignore_in_history is True
