# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Defines reusable lifecycle hooks for Falyx Actions and Commands.

This module includes:
- `ResultReporter`: A success hook that displays a formatted result with duration.
- `CircuitBreaker`: A failure-aware hook manager that prevents repeated execution
  after a configurable number of failures.

These hooks can be registered on `HookManager` instances via lifecycle stages
(`before`, `on_error`, `after`, etc.) to enhance resiliency and observability.

Intended for use with:
- Retryable or unstable actions
- Interactive CLI feedback
- Safety checks prior to execution

Example usage:
    breaker = CircuitBreaker(max_failures=3)
    hooks.register(HookType.BEFORE, breaker.before_hook)
    hooks.register(HookType.ON_ERROR, breaker.error_hook)
    hooks.register(HookType.AFTER, breaker.after_hook)

    reporter = ResultReporter()
    hooks.register(HookType.ON_SUCCESS, reporter.report)
"""

import time
from typing import Any, Callable

from falyx.context import ExecutionContext
from falyx.exceptions import CircuitBreakerOpen
from falyx.logger import logger
from falyx.themes import OneColors


class ResultReporter:
    """Reports the success of an action."""

    def __init__(self, formatter: Callable[[Any], str] | None = None):
        """
        Optional result formatter. If not provided, uses repr(result).
        """
        self.formatter = formatter or (self.default_formatter)

    def default_formatter(self, result: Any):
        """
        Default formatter for results. Converts the result to a string.
        """
        return repr(result)

    @property
    def __name__(self):
        return "ResultReporter"

    async def report(self, context: ExecutionContext):
        if not callable(self.formatter):
            raise TypeError("formatter must be callable")
        if context.result is not None:
            result_text = self.formatter(context.result)
            duration = (
                f"{context.duration:.3f}s" if context.duration is not None else "n/a"
            )
            context.console.print(
                f"[{OneColors.GREEN}]✅ '{context.name}' "
                f"completed:[/] {result_text} in {duration}."
            )


class CircuitBreaker:
    """Circuit Breaker pattern to prevent repeated failures."""

    def __init__(self, max_failures=3, reset_timeout=10):
        self.max_failures = max_failures
        self.reset_timeout = reset_timeout
        self.failures = 0
        self.open_until = None

    def before_hook(self, context: ExecutionContext):
        name = context.name
        if self.open_until:
            if time.time() < self.open_until:
                raise CircuitBreakerOpen(
                    f"Circuit open for '{name}' until {time.ctime(self.open_until)}."
                )
            else:
                logger.info("Circuit closed again for '%s'.")
                self.failures = 0
                self.open_until = None

    def error_hook(self, context: ExecutionContext):
        name = context.name
        self.failures += 1
        logger.warning(
            "CircuitBreaker: '%s' failure %s/%s.",
            name,
            self.failures,
            self.max_failures,
        )
        if self.failures >= self.max_failures:
            self.open_until = time.time() + self.reset_timeout
            logger.error(
                "Circuit opened for '%s' until %s.", name, time.ctime(self.open_until)
            )

    def after_hook(self, _: ExecutionContext):
        self.failures = 0

    def is_open(self):
        return self.open_until is not None and time.time() < self.open_until

    def reset(self):
        self.failures = 0
        self.open_until = None
        logger.info("Circuit reset.")
