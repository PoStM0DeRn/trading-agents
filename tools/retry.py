"""Retry decorators with exponential backoff and jitter."""

import functools
import logging
import random
import time
from typing import Type, Tuple, Optional, Callable

logger = logging.getLogger(__name__)


def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """Синхронный retry с exponential backoff + jitter.

    Args:
        max_retries: максимальное количество попыток
        base_delay: начальная задержка в секундах
        max_delay: максимальная задержка в секундах
        exceptions: кортеж исключений, при которых делать retry
        on_retry: callback при retry (exc, attempt)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt == max_retries - 1:
                        logger.error(f"All {max_retries} attempts failed for {func.__name__}: {e}")
                        raise
                    delay = min(base_delay * 2 ** attempt, max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter
                    logger.warning(f"Retry {attempt + 1}/{max_retries} for {func.__name__} after {total_delay:.1f}s: {e}")
                    if on_retry:
                        on_retry(e, attempt)
                    time.sleep(total_delay)
            raise last_exc
        return wrapper
    return decorator
