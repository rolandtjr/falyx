from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from falyx.hook_manager import HookManager, HookType


def make_context(*, name: str = "DemoAction", exception: Exception | None = None) -> Any:
    return SimpleNamespace(name=name, exception=exception, events=[])


def test_hook_type_choices_aliases_and_string_representation() -> None:
    assert HookType.choices() == [
        HookType.BEFORE,
        HookType.ON_SUCCESS,
        HookType.ON_ERROR,
        HookType.AFTER,
        HookType.ON_TEARDOWN,
    ]
    assert HookType(" before ") is HookType.BEFORE
    assert HookType("success") is HookType.ON_SUCCESS
    assert HookType(" ERROR ") is HookType.ON_ERROR
    assert HookType("teardown") is HookType.ON_TEARDOWN
    assert str(HookType.AFTER) == "after"


@pytest.mark.parametrize("bad_value", [7, object()])
def test_hook_type_rejects_non_string_missing_values(bad_value: object) -> None:
    with pytest.raises(ValueError, match="Invalid HookType"):
        HookType(bad_value)


def test_hook_type_rejects_unknown_string_with_valid_choices() -> None:
    with pytest.raises(ValueError) as exc_info:
        HookType("not-a-hook")

    message = str(exc_info.value)
    assert "Invalid HookType: 'not-a-hook'" in message
    assert "before" in message
    assert "on_success" in message
    assert "on_error" in message
    assert "after" in message
    assert "on_teardown" in message


def test_manager_initializes_all_hook_buckets_and_registers_aliases() -> None:
    manager = HookManager()

    assert set(manager._hooks) == set(HookType)
    assert all(hooks == [] for hooks in manager._hooks.values())

    def before_hook(context: Any) -> None:
        context.events.append("before")

    def success_hook(context: Any) -> None:
        context.events.append("success")

    manager.register(HookType.BEFORE, before_hook)
    manager.register("success", success_hook)

    assert manager._hooks[HookType.BEFORE] == [before_hook]
    assert manager._hooks[HookType.ON_SUCCESS] == [success_hook]


def test_register_rejects_invalid_hook_type() -> None:
    manager = HookManager()

    def hook(context: Any) -> None:
        context.events.append("never-called")

    with pytest.raises(ValueError, match="Invalid HookType"):
        manager.register("missing-phase", hook)


@pytest.mark.asyncio
async def test_trigger_runs_sync_and_async_hooks_in_registration_order() -> None:
    manager = HookManager()
    context = make_context()

    def sync_first(ctx: Any) -> None:
        ctx.events.append("sync-first")

    async def async_second(ctx: Any) -> None:
        ctx.events.append("async-second")

    def sync_third(ctx: Any) -> None:
        ctx.events.append("sync-third")

    manager.register("before", sync_first)
    manager.register(HookType.BEFORE, async_second)
    manager.register("before", sync_third)

    await manager.trigger(HookType.BEFORE, context)

    assert context.events == ["sync-first", "async-second", "sync-third"]


@pytest.mark.asyncio
async def test_trigger_rejects_unsupported_runtime_hook_type() -> None:
    manager = HookManager()

    with pytest.raises(ValueError, match="Unsupported hook type"):
        await manager.trigger("not-a-hook", make_context())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_trigger_logs_and_continues_after_non_error_hook_failure() -> None:
    manager = HookManager()
    context = make_context()

    def failing_hook(ctx: Any) -> None:
        ctx.events.append("failing")
        raise RuntimeError("hook exploded")

    def surviving_hook(ctx: Any) -> None:
        ctx.events.append("surviving")

    manager.register(HookType.BEFORE, failing_hook)
    manager.register(HookType.BEFORE, surviving_hook)

    await manager.trigger(HookType.BEFORE, context)

    assert context.events == ["failing", "surviving"]


@pytest.mark.asyncio
async def test_trigger_on_error_hook_failure_reraises_original_context_exception() -> (
    None
):
    manager = HookManager()
    original_error = ValueError("original failure")
    context = make_context(exception=original_error)

    def failing_error_hook(ctx: Any) -> None:
        ctx.events.append("error-hook")
        raise RuntimeError("error hook failed")

    manager.register("error", failing_error_hook)

    with pytest.raises(ValueError) as exc_info:
        await manager.trigger(HookType.ON_ERROR, context)

    assert exc_info.value is original_error
    assert isinstance(exc_info.value.__cause__, RuntimeError)
    assert str(exc_info.value.__cause__) == "error hook failed"
    assert context.events == ["error-hook"]


@pytest.mark.asyncio
async def test_trigger_on_error_requires_context_exception_when_hook_fails() -> None:
    manager = HookManager()
    context = make_context(exception=None)

    def failing_error_hook(ctx: Any) -> None:
        raise RuntimeError("error hook failed")

    manager.register(HookType.ON_ERROR, failing_error_hook)

    with pytest.raises(AssertionError, match="Context exception should be set"):
        await manager.trigger(HookType.ON_ERROR, context)


def test_clear_removes_one_hook_bucket_or_all_buckets() -> None:
    manager = HookManager()

    def before_hook(context: Any) -> None:
        context.events.append("before")

    def after_hook(context: Any) -> None:
        context.events.append("after")

    manager.register("before", before_hook)
    manager.register("after", after_hook)

    manager.clear(HookType.BEFORE)

    assert manager._hooks[HookType.BEFORE] == []
    assert manager._hooks[HookType.AFTER] == [after_hook]

    manager.clear()

    assert all(hooks == [] for hooks in manager._hooks.values())


def test_string_representation_lists_registered_hook_names_and_empty_buckets() -> None:
    manager = HookManager()

    def before_hook(context: Any) -> None:
        context.events.append("before")

    manager.register("before", before_hook)

    text = str(manager)

    assert text.startswith("<HookManager>")
    assert "before: before_hook" in text
    assert "on_success: —" in text
    assert "on_error: —" in text
    assert "after: —" in text
    assert "on_teardown: —" in text


def test_copy_copies_hook_lists_without_sharing_list_objects() -> None:
    manager = HookManager()

    def first_hook(context: Any) -> None:
        context.events.append("first")

    def second_hook(context: Any) -> None:
        context.events.append("second")

    manager.register("teardown", first_hook)

    clone = manager.copy()

    assert clone is not manager
    assert clone._hooks[HookType.ON_TEARDOWN] == [first_hook]
    assert clone._hooks[HookType.ON_TEARDOWN] is not manager._hooks[HookType.ON_TEARDOWN]

    clone.register("teardown", second_hook)

    assert manager._hooks[HookType.ON_TEARDOWN] == [first_hook]
    assert clone._hooks[HookType.ON_TEARDOWN] == [first_hook, second_hook]
