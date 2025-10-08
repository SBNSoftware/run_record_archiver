import logging
import time
from functools import wraps
from typing import Any, Callable


def performance_monitor(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        logger = logging.getLogger(func.__module__)
        start_time = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "PERF: %s.%s executed in %.2f ms.",
                func.__module__,
                func.__name__,
                duration_ms,
            )
            if args and hasattr(args[0], "carbon_client"):
                carbon_client = args[0].carbon_client
                if carbon_client and carbon_client.enabled:
                    metric_path = (
                        f"{args[0].__class__.__name__}.{func.__name__}.duration_ms"
                    )
                    carbon_client.post_metric(metric_path, duration_ms)

    return wrapper
