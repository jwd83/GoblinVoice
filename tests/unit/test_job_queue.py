from __future__ import annotations

import asyncio

import pytest

from goblinvoice.errors import QueueError
from goblinvoice.orchestrator.job_queue import JobQueue


@pytest.mark.asyncio
async def test_job_queue_processes_work() -> None:
    queue = JobQueue(worker_count=1)
    await queue.start()

    result = await queue.submit(
        name="ok",
        timeout_seconds=1.0,
        coro_factory=lambda: asyncio.sleep(0.01, result="done"),
    )

    await queue.stop()
    snap = queue.snapshot()

    assert result == "done"
    assert snap.processed == 1
    assert snap.failed == 0


@pytest.mark.asyncio
async def test_job_queue_times_out() -> None:
    queue = JobQueue(worker_count=1)
    await queue.start()

    with pytest.raises(QueueError):
        await queue.submit(
            name="timeout",
            timeout_seconds=0.01,
            coro_factory=lambda: asyncio.sleep(0.2, result="late"),
        )

    await queue.stop()
    snap = queue.snapshot()
    assert snap.failed == 1
