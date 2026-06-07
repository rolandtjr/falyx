import pytest

from falyx.action.action import Action
from falyx.action.action_group import ActionGroup
from falyx.action.chained_action import ChainedAction
from falyx.action.http_action import HTTPAction
from falyx.action.menu_action import MenuAction
from falyx.action.process_action import ProcessAction
from falyx.hook_manager import HookType
from falyx.menu import MenuOption, MenuOptionMap
from falyx.retry import RetryHandler, RetryPolicy


def _retry_hooks(action) -> list:
    return [
        hook
        for hook in action.hooks._hooks[HookType.ON_ERROR]
        if isinstance(getattr(hook, "__self__", None), RetryHandler)
    ]


def _non_retry_error_hooks(action) -> list:
    return [
        hook
        for hook in action.hooks._hooks[HookType.ON_ERROR]
        if not isinstance(getattr(hook, "__self__", None), RetryHandler)
    ]


def _before_hooks(action) -> list:
    return list(action.hooks._hooks[HookType.BEFORE])


def test_action_group_clone_recursively_isolates_nested_action_graph():
    nested_chain = ChainedAction(
        name="nested-chain",
        actions=[
            Action("step-two", lambda: "two"),
            Action("step-three", lambda: "three"),
        ],
    )
    original = ActionGroup(
        name="group",
        actions=[
            Action("step-one", lambda: "one"),
            nested_chain,
        ],
    )

    cloned = original.clone()

    assert cloned is not original
    assert cloned.actions is not original.actions
    assert len(cloned.actions) == len(original.actions)

    # Top-level children are cloned.
    assert cloned.actions[0] is not original.actions[0]
    assert cloned.actions[1] is not original.actions[1]

    # Nested action graph is also cloned.
    assert isinstance(cloned.actions[1], ChainedAction)
    assert cloned.actions[1].actions is not original.actions[1].actions
    for cloned_child, original_child in zip(
        cloned.actions[1].actions,
        original.actions[1].actions,
        strict=True,
    ):
        assert cloned_child is not original_child
        assert cloned_child.name == original_child.name

    # Mutating the clone does not mutate the original.
    cloned.actions.append(Action("step-four", lambda: "four"))
    assert len(cloned.actions) == 3
    assert len(original.actions) == 2

    cloned.actions[1].actions.append(Action("step-five", lambda: "five"))
    assert len(cloned.actions[1].actions) == 3
    assert len(original.actions[1].actions) == 2


def test_menu_action_clone_copies_menu_option_map_and_clones_contained_actions():
    menu_options = MenuOptionMap(disable_reserved=True)
    menu_options["A"] = MenuOption(
        description="Alpha",
        action=Action("alpha-action", lambda: "alpha"),
    )

    original = MenuAction(
        name="main-menu",
        menu_options=menu_options,
        title="Main Menu",
    )

    cloned = original.clone()

    assert cloned is not original
    assert cloned.menu_options is not original.menu_options

    assert cloned.menu_options["A"] is not original.menu_options["A"]
    assert cloned.menu_options["A"].description == original.menu_options["A"].description

    # Contained action should also be cloned.
    assert cloned.menu_options["A"].action is not original.menu_options["A"].action
    assert cloned.menu_options["A"].action.name == original.menu_options["A"].action.name

    # Mutating the clone should not affect the original.
    cloned.menu_options["A"].description = "Changed"
    assert original.menu_options["A"].description == "Alpha"

    cloned.menu_options["B"] = MenuOption(
        description="Beta",
        action=Action("beta-action", lambda: "beta"),
    )
    assert "B" in cloned.menu_options
    assert "B" not in original.menu_options


def test_process_action_clone_does_not_reuse_runtime_only_executor_state():
    original = ProcessAction(
        name="proc",
        action=lambda x: x + 1,
        args=(1,),
        kwargs={"y": 2},
    )

    original.executor = object()

    cloned = original.clone()

    assert cloned is not original
    assert cloned.hooks is not original.hooks
    assert cloned.args == original.args
    assert cloned.kwargs == original.kwargs

    assert cloned.executor is not original.executor


def test_http_action_clone_preserves_retry_policy_without_duplicating_spinner_hooks():
    retry_policy = RetryPolicy(max_retries=3, delay=1.5, backoff=2.0)
    retry_policy.enable_policy()

    original = HTTPAction(
        name="get-users",
        method="GET",
        url="https://example.com/api/users",
        headers={"Authorization": "Bearer token"},
        params={"page": 1},
        retry_policy=retry_policy,
        spinner=True,
    )

    before_count = len(original.hooks._hooks[HookType.BEFORE])
    teardown_count = len(original.hooks._hooks[HookType.ON_TEARDOWN])
    error_count = len(original.hooks._hooks[HookType.ON_ERROR])

    cloned = original.clone()

    assert cloned is not original
    assert cloned.hooks is not original.hooks

    assert cloned.retry_policy is not original.retry_policy
    assert cloned.retry_policy.enabled is original.retry_policy.enabled
    assert cloned.retry_policy.max_retries == original.retry_policy.max_retries
    assert cloned.retry_policy.delay == original.retry_policy.delay
    assert cloned.retry_policy.backoff == original.retry_policy.backoff

    assert len(cloned.hooks._hooks[HookType.BEFORE]) == before_count
    assert len(cloned.hooks._hooks[HookType.ON_TEARDOWN]) == teardown_count
    assert len(cloned.hooks._hooks[HookType.ON_ERROR]) == error_count


@pytest.mark.asyncio
async def test_action_clone_registers_exactly_one_retry_hook():
    async def flaky():
        return "ok"

    policy = RetryPolicy(max_retries=2, delay=0.1, backoff=2.0)
    policy.enable_policy()

    original = Action(
        "flaky",
        flaky,
        retry_policy=policy,
    )

    cloned = original.clone()

    original_retry_hooks = _retry_hooks(original)
    cloned_retry_hooks = _retry_hooks(cloned)

    assert len(original_retry_hooks) == 1
    assert len(cloned_retry_hooks) == 1

    assert cloned_retry_hooks[0] is not original_retry_hooks[0]
    assert getattr(cloned_retry_hooks[0], "__self__", None) is not getattr(
        original_retry_hooks[0], "__self__", None
    )


def test_action_clone_preserves_non_retry_hooks_without_duplication():
    calls = []

    async def custom_error_hook(context):
        calls.append(context.name)

    original = Action("demo", lambda: "ok")
    original.hooks.register(HookType.BEFORE, lambda context: None)
    original.hooks.register(HookType.ON_ERROR, custom_error_hook)

    cloned = original.clone()

    assert len(_before_hooks(cloned)) == len(_before_hooks(original))
    assert len(_non_retry_error_hooks(cloned)) == len(_non_retry_error_hooks(original))

    assert cloned.hooks is not original.hooks


def test_action_clone_copies_retry_policy_without_sharing_it():
    policy = RetryPolicy(max_retries=2, delay=0.25, backoff=3.0)
    policy.enable_policy()

    original = Action(
        "demo",
        lambda: "ok",
        retry_policy=policy,
    )

    cloned = original.clone()

    assert cloned.retry_policy is not original.retry_policy
    assert cloned.retry_policy.enabled is original.retry_policy.enabled
    assert cloned.retry_policy.max_retries == original.retry_policy.max_retries
    assert cloned.retry_policy.delay == original.retry_policy.delay
    assert cloned.retry_policy.backoff == original.retry_policy.backoff

    cloned.retry_policy.max_retries = 9
    assert original.retry_policy.max_retries == 2


@pytest.mark.asyncio
async def test_action_clone_retry_behavior_still_works_independently():
    state = {"original": 0, "clone": 0}

    async def flaky_original():
        if state["original"] == 0:
            state["original"] += 1
            raise RuntimeError("boom")
        return "original-ok"

    async def flaky_clone():
        if state["clone"] == 0:
            state["clone"] += 1
            raise RuntimeError("boom")
        return "clone-ok"

    policy = RetryPolicy(max_retries=1, delay=0.0, backoff=1.0)
    policy.enable_policy()

    original = Action("orig", flaky_original, retry_policy=policy)
    cloned = original.clone()

    cloned.action = flaky_clone

    original_result = await original()
    cloned_result = await cloned()

    assert original_result == "original-ok"
    assert cloned_result == "clone-ok"
    assert state["original"] == 1
    assert state["clone"] == 1


def test_http_action_clone_registers_exactly_one_retry_hook():
    policy = RetryPolicy(max_retries=2, delay=0.1, backoff=2.0)
    policy.enable_policy()

    original = HTTPAction(
        name="get-users",
        method="GET",
        url="https://example.com/api/users",
        retry_policy=policy,
        spinner=True,
    )

    cloned = original.clone()

    original_retry_hooks = _retry_hooks(original)
    cloned_retry_hooks = _retry_hooks(cloned)

    assert len(original_retry_hooks) == 1
    assert len(cloned_retry_hooks) == 1
    assert cloned_retry_hooks[0] is not original_retry_hooks[0]


def test_http_action_clone_copies_retry_policy_without_sharing_it():
    policy = RetryPolicy(max_retries=3, delay=1.5, backoff=2.0)
    policy.enable_policy()

    original = HTTPAction(
        name="get-users",
        method="GET",
        url="https://example.com/api/users",
        retry_policy=policy,
    )

    cloned = original.clone()

    assert cloned.retry_policy is not original.retry_policy
    assert cloned.retry_policy.enabled is original.retry_policy.enabled
    assert cloned.retry_policy.max_retries == original.retry_policy.max_retries
    assert cloned.retry_policy.delay == original.retry_policy.delay
    assert cloned.retry_policy.backoff == original.retry_policy.backoff


def test_http_action_clone_does_not_duplicate_spinner_hooks():
    policy = RetryPolicy(max_retries=1, delay=0.0, backoff=1.0)
    policy.enable_policy()

    original = HTTPAction(
        name="get-users",
        method="GET",
        url="https://example.com/api/users",
        retry_policy=policy,
        spinner=True,
    )

    cloned = original.clone()

    assert len(cloned.hooks._hooks[HookType.BEFORE]) == len(
        original.hooks._hooks[HookType.BEFORE]
    )
    assert len(cloned.hooks._hooks[HookType.ON_TEARDOWN]) == len(
        original.hooks._hooks[HookType.ON_TEARDOWN]
    )
