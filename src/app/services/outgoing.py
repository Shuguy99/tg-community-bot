import asyncio
import heapq
import time
from collections.abc import Awaitable, Callable

import structlog

from app.services.retry import retry_async

log = structlog.get_logger()


@retry_async()
async def _run(coro_factory):
    return await coro_factory()


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
    def __init__(
        self,
        bucket: TokenBucket,
        max_pending: int = 1000,
        per_chat_interval: float = 1.0,
        monotonic=time.monotonic,
    ):
        self._bucket = bucket
        self._max_pending = max_pending
        self._per_chat_interval = per_chat_interval
        self._monotonic = monotonic
        self._heap: list[tuple[int, int, Callable[[], Awaitable], int | None, bool]] = []
        self._cond = asyncio.Condition()
        self._counter = 0
        self._inflight = 0
        self._workers: list[asyncio.Task] = []
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._chat_last: dict[int, float] = {}

    async def submit(
        self,
        coro_factory: Callable[[], Awaitable],
        *,
        priority: int = 0,
        chat_id: int | None = None,
        retry: bool = True,
    ) -> None:
        async with self._cond:
            if len(self._heap) >= self._max_pending:
                worst = max(range(len(self._heap)), key=lambda i: self._heap[i][0])
                if self._heap[worst][0] <= priority:
                    log.warning("outgoing_dropped", priority=priority, chat_id=chat_id)
                    return
                log.warning("outgoing_evicted", priority=self._heap[worst][0], chat_id=chat_id)
                self._heap.pop(worst)
                heapq.heapify(self._heap)
            self._counter += 1
            heapq.heappush(self._heap, (priority, self._counter, coro_factory, chat_id, retry))
            self._cond.notify()

    async def start(self, n_workers: int = 4) -> None:
        for _ in range(n_workers):
            self._workers.append(asyncio.create_task(self._worker()))

    async def stop(self, drain: bool = True) -> None:
        if drain:
            async with self._cond:
                await self._cond.wait_for(lambda: not self._heap and self._inflight == 0)
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker(self) -> None:
        while True:
            async with self._cond:
                while not self._heap:
                    await self._cond.wait()
                _, _, coro_factory, chat_id, retry = heapq.heappop(self._heap)
                self._inflight += 1
            try:
                await self._bucket.acquire()
                if chat_id is not None:
                    await self._throttle(chat_id)
                if retry:
                    await _run(coro_factory)
                else:
                    await coro_factory()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("outgoing_task_failed", error=str(exc))
            finally:
                async with self._cond:
                    self._inflight -= 1
                    self._cond.notify_all()

    async def _throttle(self, chat_id: int) -> None:
        lock = self._chat_locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            wait = self._per_chat_interval - (self._monotonic() - self._chat_last.get(chat_id, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._chat_last[chat_id] = self._monotonic()
