import asyncio

import pytest

from backend.app.core.job_queue import SingleGpuJobQueue


@pytest.mark.asyncio
async def test_worker_survives_a_failed_job():
    completed: list[str] = []

    async def handler(run_id: str) -> None:
        if run_id == "bad":
            raise RuntimeError("expected failure")
        completed.append(run_id)

    queue = SingleGpuJobQueue(handler)
    await queue.start()
    await queue.submit("bad")
    await queue.submit("good")
    await asyncio.wait_for(queue._queue.join(), timeout=1)
    await queue.stop()
    assert completed == ["good"]
