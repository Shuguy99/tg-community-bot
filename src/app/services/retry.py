from aiogram.exceptions import TelegramRetryAfter
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential


def retry_async(attempts: int = 4, wait_min: float = 0.5, wait_max: float = 8.0):
    backoff = wait_random_exponential(multiplier=wait_min, max=wait_max)

    def _wait(retry_state):
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exc, TelegramRetryAfter):
            return float(exc.retry_after) + 0.5
        return backoff(retry_state)

    return retry(
        stop=stop_after_attempt(attempts),
        wait=_wait,
        retry=retry_if_exception_type(
            (ConnectionError, TimeoutError, OSError, TelegramRetryAfter)
        ),
        reraise=True,
    )
