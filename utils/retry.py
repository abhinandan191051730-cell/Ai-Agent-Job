import asyncio
import logging
from typing import Type, Tuple

logger = logging.getLogger(__name__)

RETRYABLE_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    asyncio.TimeoutError,
    TimeoutError,
)


class RetryableError(Exception):
    pass


async def with_retry(coro_factory, max_retries=2, base_delay=2.0,
                     retryable_exceptions=RETRYABLE_EXCEPTIONS):
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except retryable_exceptions as e:
            last_exception = e
            if attempt >= max_retries:
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning("Retry %d/%d after %.1fs: %s", attempt + 1, max_retries, delay, e)
            await asyncio.sleep(delay)
    raise last_exception
