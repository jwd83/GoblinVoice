from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from goblinvoice.errors import QueueError
from goblinvoice.types import QueueSnapshot


@dataclass(slots=True)
class _Job:
    name: str
    timeout_seconds: float
    coro_factory: Callable[[], Awaitable[Any]]
    future: asyncio.Future[Any]


class JobQueue:
    def __init__(self, *, worker_count: int = 1) -> None:
        self.worker_count = worker_count
        self._queue: asyncio.Queue[_Job | None] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._started = False
        self._inflight = 0
        self._processed = 0
        self._failed = 0

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._workers = [
            asyncio.create_task(self._worker(worker_id=index), name=f"goblinvoice-worker-{index}")
            for index in range(self.worker_count)
        ]

    async def stop(self) -> None:
        if not self._started:
            return

        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers = []
        self._started = False

    async def submit(
        self,
        *,
        name: str,
        timeout_seconds: float,
        coro_factory: Callable[[], Awaitable[Any]],
    ) -> Any:
        if not self._started:
            raise QueueError("Job queue has not been started")

        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        await self._queue.put(
            _Job(
                name=name,
                timeout_seconds=timeout_seconds,
                coro_factory=coro_factory,
                future=future,
            )
        )
        return await future

    async def _worker(self, *, worker_id: int) -> None:
        while True:
            item = await self._queue.get()
            if item is None:
                self._queue.task_done()
                return

            self._inflight += 1
            try:
                result = await asyncio.wait_for(item.coro_factory(), timeout=item.timeout_seconds)
            except TimeoutError:
                if not item.future.done():
                    item.future.set_exception(
                        QueueError(f"{item.name} timed out after {item.timeout_seconds:.1f}s")
                    )
                self._failed += 1
            except Exception as exc:  # noqa: BLE001
                if not item.future.done():
                    item.future.set_exception(exc)
                self._failed += 1
            else:
                if not item.future.done():
                    item.future.set_result(result)
                self._processed += 1
            finally:
                self._inflight -= 1
                self._queue.task_done()

    def snapshot(self) -> QueueSnapshot:
        return QueueSnapshot(
            pending=self._queue.qsize(),
            inflight=self._inflight,
            processed=self._processed,
            failed=self._failed,
        )
