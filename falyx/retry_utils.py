from falyx.action import Action, BaseAction
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
