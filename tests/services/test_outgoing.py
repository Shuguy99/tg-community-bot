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


async def _append(target, value):
    target.append(value)
