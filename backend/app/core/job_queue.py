import asyncio
import logging
from collections.abc import Awaitable, Callable

JobHandler = Callable[[str], Awaitable[None]]
logger = logging.getLogger(__name__)


class SingleGpuJobQueue:
    """One consumer serializes STATE work on the single A6000."""

    def __init__(self, handler: JobHandler):
        self._handler = handler
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker(), name="celllens-gpu-worker")

    async def stop(self) -> None:
        if self._task is not None:
            await self._queue.put(None)
            await self._task
            self._task = None

    async def submit(self, run_id: str) -> None:
        await self._queue.put(run_id)

    async def _worker(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                if run_id is None:
                    return
                try:
                    await self._handler(run_id)
                except Exception:
                    # The pipeline has persisted the task failure. Keep the shared
                    # A6000 worker alive for later submissions.
                    logger.exception("CellLens job failed: %s", run_id)
            finally:
                self._queue.task_done()
