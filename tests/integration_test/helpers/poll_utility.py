import time
from typing import Callable, Any


class TimeoutError(Exception):
    pass


def poll_until(
    condition_func: Callable[[], Any],
    timeout: float = 15.0,
    initial_delay: float = 0.2,
    backoff_factor: float = 1.5,
    max_delay: float = 2.0,
    error_message: str = "Condition not met within timeout period."
) -> Any:
    """
    Polls `condition_func` until it returns a truthy value or non-None result,
    or until `timeout` seconds have elapsed. Uses exponential backoff.
    """
    start_time = time.time()
    current_delay = initial_delay
    last_exception = None

    while (time.time() - start_time) < timeout:
        try:
            result = condition_func()
            if result:
                return result
        except Exception as e:
            last_exception = e

        time.sleep(current_delay)
        current_delay = min(current_delay * backoff_factor, max_delay)

    elapsed = time.time() - start_time
    diag_msg = f"{error_message} (Elapsed: {elapsed:.2f}s, Last error: {last_exception})"
    raise TimeoutError(diag_msg)
