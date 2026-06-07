import pytest

from falyx import Falyx
from falyx.action import Action, ChainedAction
from falyx.command import Command
from falyx.options_manager import OptionsManager


def test_seed_missing_and_override_namespace_do_not_leak():
    options = OptionsManager()
    options.set("verbose", True, "root")

    options.seed_missing({"verbose": False, "debug_hooks": False}, "root")
    assert options.get("verbose", namespace_name="root") is True
    assert options.get("debug_hooks", namespace_name="root") is False

    with options.override_namespace({"verbose": False}, "root"):
        assert options.get("verbose", namespace_name="root") is False

    assert options.get("verbose", namespace_name="root") is True


def test_command_and_action_read_options_from_expected_namespace():
    options = OptionsManager()
    options.from_mapping({"region": "us-east"}, "default")
    options.from_mapping({"never_prompt": True, "verbose": True}, "root")

    action = Action("deploy-action", lambda: "ok")
    command = Command.build(
        key="D",
        description="Deploy",
        action=action,
        options_manager=options,
    )

    command._inject_options_manager()

    assert command.get_option("region") == "us-east"
    assert command.get_option("verbose", namespace_name="root") is True

    assert action.get_option("region") == "us-east"
    assert action.get_option("verbose", namespace_name="root") is True
    assert action.never_prompt is True
    assert action.local_never_prompt is None


def test_all_objects_in_one_namespace_share_same_options_manager():
    flx = Falyx(program="root")

    chain = ChainedAction(
        name="deploy-flow",
        actions=[
            Action("step-one", lambda: "one"),
            Action("step-two", lambda: "two"),
        ],
    )
    command = flx.add_command("D", "Deploy", action=chain)

    command._inject_options_manager()

    assert flx._executor.options_manager is flx.options_manager
    assert flx.exit_command.options_manager is flx.options_manager
    assert flx.help_command.options_manager is flx.options_manager

    if flx.history_command:
        assert flx.history_command.options_manager is flx.options_manager
        assert flx.history_command.arg_parser.options_manager is flx.options_manager

    for builtin in flx.builtins.values():
        assert builtin.options_manager is flx.options_manager
        if builtin.arg_parser:
            assert builtin.arg_parser.options_manager is flx.options_manager

    assert command.options_manager is flx.options_manager
    assert command.arg_parser.options_manager is flx.options_manager

    assert chain.options_manager is flx.options_manager
    for child_action in chain.actions:
        assert child_action.options_manager is flx.options_manager


def test_nested_namespace_may_keep_distinct_options_manager_if_intended():
    root_options = OptionsManager()
    child_options = OptionsManager()

    root = Falyx(program="root", options_manager=root_options)
    child = Falyx(program="child", options_manager=child_options)
    child_command = child.add_command("D", "Deploy", action=lambda: "ok")

    root.add_submenu(
        key="C",
        description="Child Menu",
        submenu=child,
    )

    assert root.options_manager is root_options
    assert child.options_manager is child_options
    assert root.options_manager is not child.options_manager

    assert root._executor.options_manager is root_options
    assert child._executor.options_manager is child_options

    assert child_command.options_manager is child_options
    assert child_command.arg_parser.options_manager is child_options

    assert child.exit_command.options_manager is child_options
    assert child.help_command.options_manager is child_options
    if child.history_command:
        assert child.history_command.options_manager is child_options

    assert root.namespaces["C"].namespace is child


@pytest.mark.asyncio
async def test_nested_namespace_receives_temporary_root_overrides_during_routed_execution():
    root_options = OptionsManager()
    child_options = OptionsManager()

    root = Falyx(program="root", options_manager=root_options)
    child = Falyx(program="child", options_manager=child_options)
    child.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    child.options_manager.set("verbose", False, "root")

    root.add_submenu(
        key="C",
        description="Child Menu",
        submenu=child,
    )

    seen_during_dispatch = {}

    async def fake_dispatch_route(*, route, args, kwargs, execution_args, **_):
        assert route.namespace is child
        seen_during_dispatch["verbose"] = route.namespace.options_manager.get(
            "verbose", False, "root"
        )
        assert seen_during_dispatch["verbose"] is True
        return "ok"

    root._dispatch_route = fake_dispatch_route

    result = await root.execute_command("--verbose C D")

    assert result == "ok"
    assert seen_during_dispatch["verbose"] is True

    result = await root.execute_command("C --verbose D")

    assert result == "ok"
    assert seen_during_dispatch["verbose"] is True

    assert child.options_manager is child_options
    assert child.options_manager.get("verbose", False, "root") is False
    assert root.options_manager is root_options


@pytest.mark.asyncio
async def test_execute_command_applies_root_defaults_without_overwriting_existing_root_values():
    child = Falyx(program="child")
    child.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    child.options_manager.set("verbose", True, "root")

    root = Falyx(program="root")
    root.add_submenu(
        key="C",
        description="Child Menu",
        submenu=child,
    )

    async def fake_dispatch_route(*, route, args, kwargs, execution_args, **_):
        assert route.namespace is child
        assert route.root_overrides == {}
        assert route.root_defaults["verbose"] is False
        assert route.namespace.options_manager.get("verbose", False, "root") is True
        return "ok"

    root._dispatch_route = fake_dispatch_route

    result = await root.execute_command("C D")

    assert result == "ok"
    assert child.options_manager.get("verbose", False, "root") is True


@pytest.mark.asyncio
async def test_execute_command_applies_root_overrides_temporarily_and_restores_root_namespace():
    child = Falyx(program="child")
    child.add_command("D", "Deploy", action=lambda: "ok", aliases=["deploy"])

    child.options_manager.set("verbose", False, "root")

    root = Falyx(program="root")
    root.add_submenu(
        key="C",
        description="Child Menu",
        submenu=child,
    )

    seen_during_dispatch = {}

    async def fake_dispatch_route(*, route, args, kwargs, execution_args, **_):
        assert route.namespace is child
        assert route.root_overrides == {"verbose": True}
        seen_during_dispatch["verbose"] = route.namespace.options_manager.get(
            "verbose", False, "root"
        )
        assert seen_during_dispatch["verbose"] is True
        return "ok"

    root._dispatch_route = fake_dispatch_route

    result = await root.execute_command("--verbose C D")

    assert result == "ok"
    assert seen_during_dispatch["verbose"] is True

    assert child.options_manager.get("verbose", False, "root") is False
