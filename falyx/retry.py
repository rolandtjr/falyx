"""retry.py"""
import asyncio

from pydantic import BaseModel, Field

from falyx.context import ExecutionContext
from falyx.utils import logger


class RetryPolicy(BaseModel):
    max_retries: int = Field(default=3, ge=0)
    delay: float = Field(default=1.0, ge=0.0)
    backoff: float = Field(default=2.0, ge=1.0)
    enabled: bool = False

    def is_active(self) -> bool:
        """
        Check if the retry policy is active.
        :return: True if the retry policy is active, False otherwise.
        """
        return self.max_retries > 0 and self.enabled


class RetryHandler:
    def __init__(self, policy: RetryPolicy=RetryPolicy()):
        self.policy = policy

    def enable_policy(self, backoff=2, max_retries=3, delay=1):
        self.policy.enabled = True
        self.policy.max_retries = max_retries
        self.policy.delay = delay
        self.policy.backoff = backoff
        logger.info(f"🔄 Retry policy enabled: {self.policy}")

    async def retry_on_error(self, context: ExecutionContext):
        from falyx.action import Action
        name = context.name
        error = context.exception
        target = context.action

        retries_done = 0
        current_delay = self.policy.delay
        last_error = error

        if not target:
            logger.warning(f"[{name}] ⚠️ No action target. Cannot retry.")
            return

        if not isinstance(target, Action):
            logger.warning(f"[{name}] ❌ RetryHandler only supports only supports Action objects.")
            return

        if not getattr(target, "is_retryable", False):
            logger.warning(f"[{name}] ❌ Not retryable.")
            return

        if not self.policy.enabled:
            logger.warning(f"[{name}] ❌ Retry policy is disabled.")
            return

        while retries_done < self.policy.max_retries:
            retries_done += 1
            logger.info(f"[{name}] 🔄 Retrying ({retries_done}/{self.policy.max_retries}) in {current_delay}s due to '{last_error}'...")
            await asyncio.sleep(current_delay)
            try:
                result = await target.action(*context.args, **context.kwargs)
                context.result = result
                context.exception = None
                logger.info(f"[{name}] ✅ Retry succeeded on attempt {retries_done}.")
                return
            except Exception as retry_error:
                last_error = retry_error
                current_delay *= self.policy.backoff
                logger.warning(f"[{name}] ⚠️ Retry attempt {retries_done}/{self.policy.max_retries} failed due to '{retry_error}'.")

        context.exception = last_error
        logger.error(f"[{name}] ❌ All {self.policy.max_retries} retries failed.")
        return
