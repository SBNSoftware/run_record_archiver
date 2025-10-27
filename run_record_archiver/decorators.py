import logging
import time
from functools import wraps
from typing import Callable, Tuple, Type, TypeVar, Any
from .exceptions import ArchiverError
T = TypeVar('T')

def retry(max_attempts: int=3, delay_seconds: float=1.0, backoff_multiplier: float=1.0, exceptions: Tuple[Type[Exception], ...]=(ArchiverError,), log_attempts: bool=True) -> Callable[[Callable[..., T]], Callable[..., T]]:

    def decorator(func: Callable[..., T]) -> Callable[..., T]:

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            logger = logging.getLogger(func.__module__)
            last_exception = None
            current_delay = delay_seconds
            for attempt in range(1, max_attempts + 1):
                try:
                    if log_attempts and attempt > 1:
                        logger.info('Retry attempt %d/%d for %s', attempt, max_attempts, func.__name__)
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if log_attempts:
                        logger.warning('Attempt %d/%d failed for %s: %s', attempt, max_attempts, func.__name__, str(e))
                    if attempt < max_attempts:
                        if log_attempts:
                            logger.info('Retrying %s in %.1f seconds...', func.__name__, current_delay)
                        time.sleep(current_delay)
                        current_delay *= backoff_multiplier
            if log_attempts:
                logger.error('All %d attempts failed for %s', max_attempts, func.__name__)
            raise last_exception
        return wrapper
    return decorator

def retry_on_failure(max_retries: int=2, delay_seconds: float=5.0, exceptions: Tuple[Type[Exception], ...]=(Exception,)) -> Callable[[Callable[..., bool]], Callable[..., bool]]:

    def decorator(func: Callable[..., bool]) -> Callable[..., bool]:

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> bool:
            logger = logging.getLogger(func.__module__)
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if result:
                        return True
                    if attempt < max_retries:
                        logger.info('%s returned False, retrying in %d seconds (attempt %d/%d)...', func.__name__, delay_seconds, attempt + 1, max_retries + 1)
                        time.sleep(delay_seconds)
                except exceptions as e:
                    logger.warning('%s raised exception (attempt %d/%d): %s', func.__name__, attempt + 1, max_retries + 1, str(e))
                    if attempt < max_retries:
                        logger.info('Retrying in %d seconds...', delay_seconds)
                        time.sleep(delay_seconds)
                    else:
                        raise
            return False
        return wrapper
    return decorator