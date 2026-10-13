import asyncio

from app.services.outgoing import OutgoingQueue, TokenBucket


async def test_queue_runs_submitted_tasks():
    q = OutgoingQueue(TokenBucket(rate=1000, capacity=1000))
    await q.start(n_workers=2)
    results = []
    await q.submit(lambda: _append(results, 1))
    await q.submit(lambda: _append(results, 2), priority=10)
    await asyncio.sleep(0.1)
    await q.stop()
    assert results == [1, 2]


async def test_bucket_limits_calls():
    now = [0.0]
    bucket = TokenBucket(rate=10, capacity=1, monotonic=lambda: now[0])
    await bucket.acquire()
    task = asyncio.create_task(bucket.acquire())
    await asyncio.sleep(0)
    assert not task.done()
    now[0] = 0.2
    await asyncio.wait_for(task, timeout=1.0)
    assert task.done()


async def test_bounded_queue_drops_new_low_priority():
    q = OutgoingQueue(TokenBucket(rate=1000, capacity=1000), max_pending=1)
    ran = []
    await q.submit(lambda: _append(ran, "high"), priority=0)
    await q.submit(lambda: _append(ran, "low"), priority=10)
    await q.start(n_workers=1)
    await q.stop()
    assert ran == ["high"]


async def test_bounded_queue_evicts_queued_low_priority():
    q = OutgoingQueue(TokenBucket(rate=1000, capacity=1000), max_pending=1)
    ran = []
    await q.submit(lambda: _append(ran, "low"), priority=10)
    await q.submit(lambda: _append(ran, "high"), priority=0)
    await q.start(n_workers=1)
    await q.stop()
    assert ran == ["high"]


async def test_per_chat_throttle_spaces_calls():
    q = OutgoingQueue(TokenBucket(rate=1000, capacity=1000), per_chat_interval=0.05)
    times = []

    async def record():
        times.append(asyncio.get_running_loop().time())

    await q.start(n_workers=2)
    await q.submit(record, chat_id=1)
    await q.submit(record, chat_id=1)
    await q.stop()
    assert len(times) == 2
    assert times[1] - times[0] >= 0.04


async def _append(target, value):
    target.append(value)
