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
        # An injected runner is a test/embedding adapter. Production defaults to a
        # durable queue consumed only by the separate worker command.
        self.embedded = runner is not None or container.settings.worker_mode == "embedded"
        self.task = None
        self.active_id = None
        self.claim = None

    def recover(self) -> None:
        if self.embedded:
            self.store.recover_expired()

    async def start(self, request: dict) -> dict:
        if self.container.settings.worker_mode == "disabled":
            raise RuntimeError("计算 worker 已禁用")
        if request.get("dataset_id"):
            from backend.app.services.dataset_registry import dataset_analysis_request

            request = await asyncio.to_thread(dataset_analysis_request, self.root, request)
        elif request.get("import_id"):
            from backend.app.services.controlled_import import import_analysis_request

            request = await asyncio.to_thread(import_analysis_request, self.root, request)
        else:
            pair = await asyncio.to_thread(
                pair_detail, self.container, request["cell_line"], request["perturbation"]
            )
            if pair["source_status"] != "measured" or not pair["source_cell_count"]:
                raise ValueError("固定版本目录中未确认该组合有实测数据；请先核对数据覆盖目录")
            request = {
                **request,
                "source_cell_count": pair["source_cell_count"],
                "source": dict(SOURCE),
                "source_catalog_sha256": file_sha256(self.root / "data/registry/perturbation_catalog.json")
                if (self.root / "data/registry/perturbation_catalog.json").is_file()
                else None,
            }
        request = {**request, "id": "measured_" + uuid4().hex[:24]}
        row = self.store.create(request)
        if self.embedded and (not self.task or self.task.done()):
            self.task = asyncio.create_task(self._drain())
        return row

    async def _drain(self):
        while await self.run_once():
            pass

    async def run_once(self) -> bool:
        try:
            resource = ResourceLease(self.base / ".cpu-worker.lock")
        except RuntimeError:
            return False
        try:
            self.store.recover_expired()
            claim = self.store.claim(
                self.container.settings.worker_id, self.container.settings.job_lease_seconds
            )
            if not claim:
                return False
            self.active_id, self.claim = claim["id"], claim
            await self._run(claim)
            return True
        finally:
            resource.close()

    async def _run(self, claim):
        request = claim["request"]
        identifier = request["id"]
        token = claim["token"]
        staging = self.base / f".{identifier}.attempt-{claim['attempt_no']}-{token}.partial"
        final = result_directory(self.root, identifier)

        def report(progress, message):
            self.store.owned_update(
                identifier,
                token,
                status="analysing" if progress >= 30 else "preparing",
                progress=max(0, min(99, int(progress))),
                message=str(message)[:1000],
            )

        compute = None
        try:
            if not final.exists():
                staging.mkdir(parents=True, exist_ok=False)
                atomic_write_json(staging / "request.json", request)
                compute = asyncio.create_task(self.runner(request, staging, final, report))
                interval = max(0.25, min(5, self.container.settings.job_lease_seconds / 3))
                while not compute.done():
                    done, _ = await asyncio.wait({compute}, timeout=interval)
                    if not self.store.heartbeat(identifier, token, self.container.settings.job_lease_seconds):
                        compute.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await compute
                        self.store.finish(identifier, token, "cancelled", message="实测分析已取消")
                        return
                    if done:
                        break
                await compute

            def publish():
                # Atomic directory rename is inside the conditional DB write
                # transaction. A stale attempt can neither publish nor complete.
                if not final.exists():
                    staging.replace(final)
                digest = file_sha256(final / "manifest.json")
                _, _, manifest = verified_result(self.root, identifier, digest)
                if manifest.get("request") != request:
                    raise ValueError("恢复结果与当前任务输入不匹配")
                return {"manifest_sha256": digest}

            completed = await asyncio.to_thread(
                self.store.finish,
                identifier,
                token,
                "completed",
                publish=publish,
                progress=100,
                message="实测数据分析完成",
            )
            if not completed:
                # Cancellation may commit between the last heartbeat and finish.
                self.store.finish(identifier, token, "cancelled", message="实测分析已取消")
        except asyncio.CancelledError:
            if compute and not compute.done():
                compute.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await compute
            # An explicit cancellation becomes terminal; process shutdown leaves
            # the attempt for lease-based recovery instead of rewriting history.
            row, _ = self.store.get(identifier)
            if row["cancel_requested"]:
                self.store.finish(identifier, token, "cancelled", message="实测分析已取消")
            raise
        except Exception as exc:
            failed = self.store.finish(
                identifier, token, "failed", message="实测分析失败，可重试", error_message=str(exc)[:2000]
            )
            if not failed:
                self.store.finish(identifier, token, "cancelled", message="实测分析已取消")
        finally:
            if compute and not compute.done():
                compute.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await compute
            self._release()

    def _release(self):
        self.claim, self.active_id = None, None

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
            "--no-publish",
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
        row["attempts"] = self.store.attempts(identifier)
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
        self.store.cancel(identifier)
        if self.embedded and self.active_id == identifier and self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        return self.get(identifier)

    async def close(self):
        if self.embedded and self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
