import asyncio
import logging

from backend.app.core.errors import JobAlreadyClaimedError, ScientificContractError
from backend.app.user_data.analysis import UserAnalysisService
from backend.app.user_data.store import UserDataStore

logger = logging.getLogger(__name__)


class UserAnalysisWorker:
    """Durable CPU queue, independent of STATE's GPU availability."""

    def __init__(self, store: UserDataStore, service: UserAnalysisService):
        self.store = store
        self.service = service
        self.task: asyncio.Task | None = None
        self.stopping = asyncio.Event()

    async def start(self) -> None:
        self.stopping.clear()
        self.task = asyncio.create_task(self.loop(), name="celllens-user-analysis-worker")

    async def stop(self) -> None:
        self.stopping.set()
        if self.task:
            await self.task
            self.task = None

    async def loop(self) -> None:
        while not self.stopping.is_set():
            await asyncio.to_thread(self.tick)
            try:
                await asyncio.wait_for(self.stopping.wait(), timeout=1)
            except TimeoutError:
                pass

    def tick(self) -> None:
        try:
            with self.store.runtime.named_lock("celllens:user-analysis-worker", timeout_seconds=0):
                pending = self.store.next_job()
                if pending is None:
                    return
                job, dataset = pending
                try:
                    artifacts = self.service.run(
                        job, dataset, self.service.settings.user_analysis_root / job["id"]
                    )
                    self.store.finish(job["id"], artifacts=artifacts)
                except Exception as exc:
                    logger.exception("User data analysis failed: %s", job["id"])
                    message = (
                        str(exc)
                        if isinstance(exc, (ValueError, ScientificContractError))
                        else ("分析执行失败，请管理员检查服务日志和依赖配置。")
                    )
                    self.store.finish(job["id"], error=message[:1500])
        except JobAlreadyClaimedError:
            pass
        except Exception:
            logger.exception("User data queue cannot access its durable store")
