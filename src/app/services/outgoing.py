import asyncio
import time
from collections.abc import Awaitable, Callable

import structlog

log = structlog.get_logger()


class TokenBucket:
    def __init__(self, rate: float = 25.0, capacity: int = 25, monotonic=time.monotonic):
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._monotonic = monotonic
        self._last = monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, n: int = 1) -> None:
        while True:
            async with self._lock:
                now = self._monotonic()
                elapsed = now - self._last
                self._last = now
                self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
                if self._tokens >= n:
                    self._tokens -= n
                    return
                wait = (n - self._tokens) / self._rate
            await asyncio.sleep(wait)


class OutgoingQueue:
    def __init__(self, bucket: TokenBucket):
        self._bucket = bucket
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._workers: list[asyncio.Task] = []
        self._counter = 0

    async def submit(self, coro_factory: Callable[[], Awaitable], *, priority: int = 0) -> None:
        self._counter += 1
        await self._queue.put((priority, self._counter, coro_factory))

    async def start(self, n_workers: int = 4) -> None:
        for _ in range(n_workers):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self, drain: bool = True) -> None:
        if drain:
            await self._queue.join()
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker(self) -> None:
        while True:
            _, _, coro_factory = await self._queue.get()
            try:
                await self._bucket.acquire()
                await coro_factory()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("outgoing_task_failed", error=str(exc))
            finally:
                self._queue.task_done()
