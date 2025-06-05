# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""debug.py"""
from falyx.context import ExecutionContext
from falyx.hook_manager import HookManager, HookType
from falyx.logger import logger


def log_before(context: ExecutionContext):
    """Log the start of an action."""
    args = ", ".join(map(repr, context.args))
    kwargs = ", ".join(f"{key}={value!r}" for key, value in context.kwargs.items())
    signature = ", ".join(filter(None, [args, kwargs]))
    logger.info("[%s] Starting -> %s(%s)", context.name, context.action, signature)


def log_success(context: ExecutionContext):
    """Log the successful completion of an action."""
    result_str = repr(context.result)
    if len(result_str) > 100:
        result_str = f"{result_str[:100]} ..."
    logger.debug("[%s] Success -> Result: %s", context.name, result_str)


def log_after(context: ExecutionContext):
    """Log the completion of an action, regardless of success or failure."""
    logger.debug("[%s] Finished in %.3fs", context.name, context.duration)


def log_error(context: ExecutionContext):
    """Log an error that occurred during the action."""
    logger.error(
        "[%s] Error (%s): %s",
        context.name,
        type(context.exception).__name__,
        context.exception,
        exc_info=True,
    )


def register_debug_hooks(hooks: HookManager):
    hooks.register(HookType.BEFORE, log_before)
    hooks.register(HookType.AFTER, log_after)
    hooks.register(HookType.ON_SUCCESS, log_success)
    hooks.register(HookType.ON_ERROR, log_error)
