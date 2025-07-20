# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""
Implements retry logic for Falyx Actions using configurable retry policies.

This module defines:
- `RetryPolicy`: A configurable model controlling retry behavior (delay, backoff, jitter).
- `RetryHandler`: A hook-compatible class that manages retry attempts for failed actions.

Used to automatically retry transient failures in leaf-level `Action` objects
when marked as retryable. Integrates with the Falyx hook lifecycle via `on_error`.

Supports:
- Exponential backoff with optional jitter
- Manual or declarative policy control
- Per-action retry logging and recovery

Example:
    handler = RetryHandler(RetryPolicy(max_retries=5, delay=1.0))
    action.hooks.register(HookType.ON_ERROR, handler.retry_on_error)
"""
from __future__ import annotations

import asyncio
import random

from pydantic import BaseModel, Field

from falyx.context import ExecutionContext
from falyx.logger import logger


class RetryPolicy(BaseModel):
    """
    Defines a retry strategy for Falyx `Action` objects.

    This model controls whether an action should be retried on failure, and how:
    - `max_retries`: Maximum number of retry attempts.
    - `delay`: Initial wait time before the first retry (in seconds).
    - `backoff`: Multiplier applied to the delay after each failure (≥ 1.0).
    - `jitter`: Optional random noise added/subtracted from delay to reduce thundering herd issues.
    - `enabled`: Whether this policy is currently active.

    Retry is only triggered for leaf-level `Action` instances marked with `is_retryable=True`
    and registered with an appropriate `RetryHandler`.

    Example:
        RetryPolicy(max_retries=3, delay=1.0, backoff=2.0, jitter=0.2, enabled=True)

    Use `enable_policy()` to activate the policy after construction.

    See Also:
        - `RetryHandler`: Executes retry logic based on this configuration.
        - `HookType.ON_ERROR`: The hook type used to trigger retries.
    """

    max_retries: int = Field(default=3, ge=0)
    delay: float = Field(default=1.0, ge=0.0)
    backoff: float = Field(default=2.0, ge=1.0)
    jitter: float = Field(default=0.0, ge=0.0)
    enabled: bool = False

    def enable_policy(self) -> None:
        """
        Enable the retry policy.
        :return: None
        """
        self.enabled = True

    def is_active(self) -> bool:
        """
        Check if the retry policy is active.
        :return: True if the retry policy is active, False otherwise.
        """
        return self.max_retries > 0 and self.enabled


class RetryHandler:
    """
    Executes retry logic for Falyx actions using a provided `RetryPolicy`.

    This class is intended to be registered as an `on_error` hook. It will
    re-attempt the failed `Action`'s `action` method using the args/kwargs from
    the failed context, following exponential backoff and optional jitter.

    Only supports retrying leaf `Action` instances (not ChainedAction or ActionGroup)
    where `is_retryable=True`.

    Attributes:
        policy (RetryPolicy): The retry configuration controlling timing and limits.

    Example:
        handler = RetryHandler(RetryPolicy(max_retries=3, delay=1.0, enabled=True))
        action.hooks.register(HookType.ON_ERROR, handler.retry_on_error)

    Notes:
        - Retries are not triggered if the policy is disabled or `max_retries=0`.
        - All retry attempts and final failure are logged automatically.
    """

    def __init__(self, policy: RetryPolicy = RetryPolicy()):
        self.policy = policy

    def enable_policy(
        self,
        max_retries: int = 3,
        delay: float = 1.0,
        backoff: float = 2.0,
        jitter: float = 0.0,
    ) -> None:
        self.policy.enabled = True
        self.policy.max_retries = max_retries
        self.policy.delay = delay
        self.policy.backoff = backoff
        self.policy.jitter = jitter
        logger.info("Retry policy enabled: %s", self.policy)

    async def retry_on_error(self, context: ExecutionContext) -> None:
        from falyx.action import Action

        name = context.name
        error = context.exception
        target = context.action

        retries_done = 0
        current_delay = self.policy.delay
        last_error = error

        if not target:
            logger.warning("[%s] No action target. Cannot retry.", name)
            return None

        if not isinstance(target, Action):
            logger.warning(
                "[%s] RetryHandler only supports only supports Action objects.", name
            )
            return None

        if not getattr(target, "is_retryable", False):
            logger.warning("[%s] Not retryable.", name)
            return None

        if not self.policy.enabled:
            logger.warning("[%s] Retry policy is disabled.", name)
            return None

        while retries_done < self.policy.max_retries:
            retries_done += 1

            sleep_delay = current_delay
            if self.policy.jitter > 0:
                sleep_delay += random.uniform(-self.policy.jitter, self.policy.jitter)
            logger.debug(
                "[%s] Error: %s",
                name,
                last_error,
            )
            logger.info(
                "[%s] Retrying (%s/%s) in %ss due to '%s'...",
                name,
                retries_done,
                self.policy.max_retries,
                current_delay,
                last_error.__class__.__name__,
            )
            await asyncio.sleep(current_delay)
            try:
                result = await target.action(*context.args, **context.kwargs)
                context.result = result
                context.exception = None
                logger.info("[%s] Retry succeeded on attempt %s.", name, retries_done)
                return None
            except Exception as retry_error:
                last_error = retry_error
                current_delay *= self.policy.backoff
                logger.debug(
                    "[%s] Error: %s",
                    name,
                    retry_error,
                )
                logger.warning(
                    "[%s] Retry attempt %s/%s failed due to '%s'.",
                    name,
                    retries_done,
                    self.policy.max_retries,
                    retry_error.__class__.__name__,
                )

        context.exception = last_error
        logger.error("[%s] All %s retries failed.", name, self.policy.max_retries)
