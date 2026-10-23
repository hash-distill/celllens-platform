"""One bounded CPU analysis at a time, with durable history and cancellation."""

import asyncio
import contextlib
import json
import os
import subprocess
import sys
from uuid import uuid4

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.measured_results import result_directory, verified_result
from backend.app.services.measured_store import ACTIVE, MeasuredStore
from backend.app.services.perturbation_catalog import SOURCE, pair_detail
from backend.app.services.resource_downloads import ResourceLease


class MeasuredJobs:
    def __init__(self, container, *, runner=None):
        self.container = container
        self.root = container.settings.project_root.resolve()
        self.store = MeasuredStore(container.store.session_factory)
        self.base = self.root / "data/derived/measured"
        self.runner = runner or self._subprocess
        self.task = None
        self.active_id = None
        self.lease = None

    def recover(self) -> None:
        try:
            lease = ResourceLease(self.base / "analysis.lock")
        except RuntimeError:
            return  # Another API instance owns the live job.
        try:
            self.store.interrupt_active()
        finally:
            lease.close()

    async def start(self, request: dict) -> dict:
        pair = await asyncio.to_thread(
            pair_detail, self.container, request["cell_line"], request["perturbation"]
        )
        if pair["source_status"] != "measured" or not pair["source_cell_count"]:
            raise ValueError("固定版本目录中未确认该组合有实测数据；请先核对数据覆盖目录")
        if self.task and not self.task.done():
            raise RuntimeError("已有实测分析正在运行，请等待完成或取消后重试")
        lease = ResourceLease(self.base / "analysis.lock")
        try:
            request = {
                **request,
                "id": "measured_" + uuid4().hex[:24],
                "source_cell_count": pair["source_cell_count"],
                "source": dict(SOURCE),
                "source_catalog_sha256": file_sha256(self.root / "data/registry/perturbation_catalog.json")
                if (self.root / "data/registry/perturbation_catalog.json").is_file()
                else None,
            }
            row = self.store.create(request)
            self.lease = lease
            self.active_id = request["id"]
            self.task = asyncio.create_task(self._run(request))
            return row
        except BaseException:
            lease.close()
            raise

    async def _run(self, request):
        identifier = request["id"]
        staging = self.base / f".{identifier}.partial"
        final = result_directory(self.root, identifier)

        def report(progress, message):
            self.store.update(
                identifier,
                status="analysing" if progress >= 30 else "preparing",
                progress=max(0, min(99, int(progress))),
                message=str(message)[:1000],
            )

        try:
            self.store.update(identifier, status="preparing", message="准备所选组合的真实数据")
            staging.mkdir(parents=True, exist_ok=False)
            atomic_write_json(staging / "request.json", request)
            await self.runner(request, staging, final, report)
            digest = file_sha256(final / "manifest.json")
            await asyncio.to_thread(verified_result, self.root, identifier, digest)
            self.store.update(
                identifier,
                status="completed",
                progress=100,
                message="实测数据分析完成",
                manifest_sha256=digest,
            )
        except asyncio.CancelledError:
            self.store.update(identifier, status="cancelled", message="实测分析已取消，可创建新分析重试")
            raise
        except Exception as exc:
            self.store.update(
                identifier, status="failed", message="实测分析失败，可重试", error_message=str(exc)[:2000]
            )
        finally:
            self._release()

    def _release(self):
        if self.lease:
            self.lease.close()
        self.lease, self.active_id = None, None

    async def _subprocess(self, request, staging, final, report):
        environment = os.environ.copy()
        environment.update({"OMP_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4", "NUMBA_NUM_THREADS": "4"})
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "backend.app.services.measured_worker",
            "--root",
            str(self.root),
            "--request-file",
            str(staging / "request.json"),
            "--parent-pid",
            str(os.getpid()),
            cwd=self.root,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        error = "实测计算进程退出，请检查网络和分析依赖"

        async def consume():
            nonlocal error
            stdout = process.stdout
            assert stdout is not None
            while line := await stdout.readline():
                try:
                    value = json.loads(line)
                    if "progress" in value:
                        report(value["progress"], value["message"])
                    if "error" in value:
                        error = value["error"]
                except (ValueError, KeyError, TypeError):
                    pass  # Scientific packages may print non-JSON diagnostics.
            await process.wait()

        try:
            await asyncio.wait_for(consume(), timeout=3600)
            if process.returncode != 0:
                raise ValueError(error)
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5)
                except TimeoutError:
                    process.kill()
                    await process.wait()

    def get(self, identifier: str) -> dict:
        result_directory(self.root, identifier)
        row, digest = self.store.get(identifier)
        if row["status"] == "completed":
            _, row["summary"], _ = verified_result(self.root, identifier, digest)
        return row

    def result(self, identifier: str):
        row, digest = self.store.get(identifier)
        if row["status"] != "completed":
            raise ValueError("实测分析尚未完成")
        return verified_result(self.root, identifier, digest)

    def list(self, limit=20, offset=0) -> dict:
        return self.store.list(limit, offset)

    async def cancel(self, identifier: str) -> dict:
        row, _ = self.store.get(identifier)
        if row["status"] not in ACTIVE:
            return self.get(identifier)
        if self.active_id != identifier or not self.task:
            raise RuntimeError("该实测分析由另一个服务进程执行，请在原服务取消")
        self.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.task
        # Cancellation before the coroutine's first instruction still releases the lease.
        self.store.update(identifier, status="cancelled", message="实测分析已取消")
        self._release()
        return self.get(identifier)

    async def close(self):
        if self.active_id:
            await self.cancel(self.active_id)
