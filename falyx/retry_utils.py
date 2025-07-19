# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Utilities for enabling retry behavior across Falyx actions.

This module provides a helper to recursively apply a `RetryPolicy` to an action and its
nested children (e.g. `ChainedAction`, `ActionGroup`), and register the appropriate
`RetryHandler` to hook into error handling.

Includes:
- `enable_retries_recursively`: Attaches a retry policy and error hook to all eligible actions.
"""
from falyx.action.action import Action
from falyx.action.base_action import BaseAction
from falyx.hook_manager import HookType
from falyx.retry import RetryHandler, RetryPolicy


def enable_retries_recursively(action: BaseAction, policy: RetryPolicy | None):
    if not policy:
        policy = RetryPolicy(enabled=True)
    if isinstance(action, Action):
        action.retry_policy = policy
        action.retry_policy.enabled = True
        action.hooks.register(HookType.ON_ERROR, RetryHandler(policy).retry_on_error)

    if hasattr(action, "actions"):
        for sub in action.actions:
            enable_retries_recursively(sub, policy)
