# Falyx CLI Framework — (c) 2025 rtj.dev LLC — MIT Licensed
"""retry.py"""
from __future__ import annotations

import asyncio
import random

from pydantic import BaseModel, Field

from falyx.context import ExecutionContext
from falyx.logger import logger


class RetryPolicy(BaseModel):
    """RetryPolicy"""

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
    """RetryHandler class to manage retry policies for actions."""

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

            logger.info(
                "[%s] Retrying (%s/%s) in %ss due to '%s'...",
                name,
                retries_done,
                self.policy.max_retries,
                current_delay,
                last_error,
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
                logger.warning(
                    "[%s] Retry attempt %s/%s failed due to '%s'.",
                    name,
                    retries_done,
                    self.policy.max_retries,
                    retry_error,
                )

        context.exception = last_error
        logger.error("[%s] All %s retries failed.", name, self.policy.max_retries)
