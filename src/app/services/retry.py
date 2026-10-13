from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_random_exponential


def retry_async(attempts: int = 4, wait_min: float = 0.5, wait_max: float = 8.0):
    return retry(
        stop=stop_after_attempt(attempts),
        wait=wait_random_exponential(multiplier=wait_min, max=wait_max),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
        reraise=True,
    )
