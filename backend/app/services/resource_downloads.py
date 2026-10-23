"""Pinned inference resources: bounded downloads, durable progress and atomic publication."""

import asyncio
import contextlib
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

from backend.app.core.errors import AssetNotReadyError, RegistryError
from backend.app.core.registry import AssetRegistry, RegistryEntry
from backend.app.core.run_manifest import atomic_write_json, file_sha256

CATALOG = Path(__file__).resolve().parents[1] / "resources/inference_assets.json"
ACTIVE = {"queued", "downloading", "verifying", "preparing_control"}


def safe_target(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()) or target == root.resolve():
        raise ValueError("Resource path is outside project directory")
    return target


def allowed_url(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    return bool(
        parsed.scheme == "https"
        and not parsed.username
        and not parsed.password
        and (host == "huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co"))
    )


async def download_asset(root: Path, spec: dict, client: httpx.AsyncClient, progress: Any) -> None:
    target = safe_target(root, spec["target"])
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    if not partial.resolve().is_relative_to(root.resolve()):
        raise ValueError("Partial resource path is outside project directory")
    expected_size = spec["size_bytes"]
    offset = partial.stat().st_size if partial.is_file() else 0
    if offset > expected_size:
        partial.unlink()
        offset = 0
    if offset < expected_size:
        url = spec["url"]
        headers = {"Accept-Encoding": "identity"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        for _ in range(8):
            if not allowed_url(url):
                raise ValueError("下载来源不在固定官方来源范围")
            async with client.stream("GET", url, headers=headers, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                if response.status_code == 206:
                    match = re.fullmatch(
                        r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("content-range", "")
                    )
                    if not match or tuple(map(int, match.groups())) != (
                        offset,
                        expected_size - 1,
                        expected_size,
                    ):
                        raise ValueError("下载范围响应不匹配，请重试")
                elif response.status_code == 200:
                    offset = 0  # Server ignored Range: safely restart, never append a full response.
                else:
                    raise ValueError(f"官方来源返回 HTTP {response.status_code}，请检查网络后重试")
                with partial.open("ab" if offset else "wb") as stream:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        offset += len(chunk)
                        if offset > expected_size:
                            raise ValueError("下载文件超过固定版本的大小")
                        stream.write(chunk)
                        progress(offset)
                break
        else:
            raise ValueError("下载来源重定向次数过多")
    if not partial.is_file() or partial.stat().st_size != expected_size:
        raise ValueError("下载文件不完整，可重试续传")
    digest = await asyncio.to_thread(file_sha256, partial)
    if digest != spec["sha256"]:
        partial.unlink()
        raise ValueError("下载文件 SHA-256 校验失败，未启用该文件")
    # Existing invalid bytes remain recoverable; valid originals are skipped by the manager.
    if target.exists():
        backup = target.with_name(target.name + f".replaced-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}")
        target.replace(backup)
    partial.replace(target)
    progress(expected_size)


class ResourceLease:
    """OS-released lock, including after a crashed process; one installer per project."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = path.open("a+b")
        self.handle.seek(0, 2)
        if not self.handle.tell():
            self.handle.write(b"0")
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.handle.close()
            raise RuntimeError("另一个服务进程正在准备资源，请稍后重试") from exc

    def close(self) -> None:
        self.handle.close()


class ResourceManager:
    def __init__(
        self,
        container: Any,
        *,
        catalog: dict | None = None,
        transport: Any = None,
        control_preparer: Any = None,
    ):
        self.container = container
        self.root = container.settings.project_root.resolve()
        self.catalog = catalog or json.loads(CATALOG.read_text(encoding="utf-8"))
        self.packs = {row["cell_line"]: row for row in self.catalog["packs"]}
        self.state_path = self.root / "data/derived/resource-downloads/jobs.json"
        self.transport, self.control_preparer = transport, control_preparer
        self.task: asyncio.Task | None = None
        self.active_cell: str | None = None
        self.lease: ResourceLease | None = None
        try:
            saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        self.jobs = {cell: saved.get(cell, {"status": "idle"}) for cell in self.packs}
        self.refresh_external()

    def refresh_external(self) -> None:
        if self.task and not self.task.done():
            return
        try:
            saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.jobs = {cell: saved.get(cell, {"status": "idle"}) for cell in self.packs}
        # A second API process must see a control registered by the installer.
        if any(job["status"] == "completed" for job in self.jobs.values()):
            registry = self.container.registry
            registry.datasets = AssetRegistry(self.root, registry.registry_root).datasets
        running = next((cell for cell, job in self.jobs.items() if job["status"] in ACTIVE), None)
        if not running:
            self.active_cell = None
            return
        try:
            probe = ResourceLease(self.state_path.parent / "download.lock")
        except RuntimeError:
            self.active_cell = running  # Another process owns the live installation.
            return
        probe.close()
        self.active_cell = None
        for job in self.jobs.values():
            if job["status"] in ACTIVE:
                job.update(status="interrupted", message="上次准备被中断，可重试继续下载")

    def update(self, cell: str, **changes: Any) -> None:
        self.jobs[cell].update(changes, updated_at=datetime.now(UTC).isoformat())
        atomic_write_json(self.state_path, self.jobs)

    def file_valid(self, spec: dict) -> bool:
        entry = RegistryEntry({"path": spec["target"], "sha256": spec["sha256"]}, self.root)
        return self.container.registry.asset_is_valid_cached(entry, "path", "sha256")

    def control_valid(self, cell: str) -> bool:
        try:
            registry = self.container.registry
            return registry.asset_is_valid_cached(
                registry.dataset_for(cell), "control_path", "control_sha256"
            )
        except (ValueError, KeyError, RegistryError, AssetNotReadyError):
            return False

    def snapshot(self) -> dict:
        self.refresh_external()
        output = []
        for cell, pack in self.packs.items():
            files = []
            for spec in pack["files"]:
                path = safe_target(self.root, spec["target"])
                valid = self.file_valid(spec)
                files.append(
                    {
                        "name": spec["name"],
                        "size_bytes": spec["size_bytes"],
                        "status": "verified" if valid else "invalid" if path.exists() else "missing",
                    }
                )
            control = self.control_valid(cell)
            output.append(
                {
                    "cell_line": cell,
                    "files": files,
                    "size_bytes": sum(x["size_bytes"] for x in files),
                    "remaining_bytes": sum(x["size_bytes"] for x in files if x["status"] != "verified"),
                    "weights_ready": all(x["status"] == "verified" for x in files),
                    "control_ready": control,
                    "ready": control and all(x["status"] == "verified" for x in files),
                    "license": pack["license"],
                    "source_url": pack["source_url"],
                    "job": dict(self.jobs[cell]),
                }
            )
        return {
            "items": output,
            # Derive activity from the same copied jobs: a task may finish while
            # later backgrounds are being hashed in this worker thread.
            "active_cell": next((row["cell_line"] for row in output if row["job"]["status"] in ACTIVE), None),
            "can_cancel": bool(self.task and not self.task.done()),
            "download_location": "运行 CellLens 后端的机器 / 当前项目目录",
            "control_source": self.catalog.get("control_source", {}),
        }

    async def start(self, cell: str, accepted_license: bool) -> dict:
        if cell not in self.packs or not accepted_license:
            raise ValueError("请选择支持的背景，并确认已阅读上游资源许可")
        if self.task and not self.task.done():
            raise RuntimeError("已有资源正在准备，请完成或取消后再开始")
        lease = ResourceLease(self.state_path.parent / "download.lock")
        try:
            try:
                saved = json.loads(self.state_path.read_text(encoding="utf-8"))
                self.jobs = {name: saved.get(name, {"status": "idle"}) for name in self.packs}
            except (OSError, ValueError):
                pass
            if (
                shutil.disk_usage(self.root).free
                < sum(x["size_bytes"] for x in self.packs[cell]["files"]) * 2
            ):
                raise ValueError("可用磁盘空间不足，请至少保留两份所选模型大小的空间")
            self.lease, self.active_cell = lease, cell
            self.update(
                cell,
                status="queued",
                message="准备检查已有资源",
                downloaded_bytes=0,
                total_bytes=sum(x["size_bytes"] for x in self.packs[cell]["files"]),
                current_file="",
            )
            self.task = asyncio.create_task(self.run(cell))
        except BaseException:
            lease.close()
            self.lease, self.active_cell = None, None
            raise
        return dict(self.jobs[cell])

    async def run(self, cell: str) -> None:
        done = 0
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60, connect=20), transport=self.transport, trust_env=False
            ) as client:
                files = sorted(
                    self.packs[cell]["files"], key=lambda spec: spec["name"] == "checkpoints/final.ckpt"
                )
                for spec in files:
                    self.update(cell, status="verifying", current_file=spec["name"], message="核验已有文件")
                    if not await asyncio.to_thread(self.file_valid, spec):
                        self.update(cell, status="downloading", message="从固定官方版本下载")
                        last = -1

                        def progress(amount: int, total=spec["size_bytes"], previous=done) -> None:
                            nonlocal last
                            # At most ~100 durable updates per file, rather than per network chunk.
                            percent = amount * 100 // max(1, total)
                            if percent != last:
                                last = percent
                                self.update(cell, downloaded_bytes=previous + amount)

                        await download_asset(self.root, spec, client, progress)
                    done += spec["size_bytes"]
                    self.update(cell, downloaded_bytes=done)
            if not await asyncio.to_thread(self.control_valid, cell):
                self.update(
                    cell,
                    status="preparing_control",
                    current_file="control.h5ad",
                    message="按当前背景提取真实非靶向对照，无需下载完整 atlas",
                )
                output = safe_target(
                    self.root, f"data/derived/resource-downloads/{cell}/{uuid4().hex}/control.h5ad"
                )
                output.parent.mkdir(parents=True, exist_ok=True)
                if self.control_preparer:
                    await self.control_preparer(
                        cell, output, lambda message: self.update(cell, message=message)
                    )
                else:
                    from backend.app.services.resource_control import run_control_process

                    await run_control_process(
                        self.root, cell, output, lambda message: self.update(cell, message=message)
                    )
                # No await in the commit phase: cancellation must not release the
                # installer lock while a detached thread is changing the registry.
                self.register_control(cell, output)
            self.update(
                cell, status="completed", current_file="", message="资源已核验，可返回工作台检查推理条件"
            )
        except asyncio.CancelledError:
            self.update(cell, status="cancelled", message="已取消，可重试续传已下载的权重")
        except (ValueError, RuntimeError) as exc:
            self.update(cell, status="failed", message=str(exc))
        except Exception:
            self.update(cell, status="failed", message="资源准备失败，请检查网络、磁盘和推理依赖后重试")
        finally:
            if self.lease:
                self.lease.close()
            self.lease, self.active_cell = None, None

    def register_control(self, cell: str, output: Path) -> None:
        registry = self.container.registry
        path = registry.registry_root / "datasets.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        current = next(row for row in document["datasets"] if row["cell_line"] == cell)
        digest = file_sha256(output)
        target = safe_target(
            self.root, f"data/raw/replogle-{cell.lower()}/control-managed-{digest[:16]}.h5ad"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and file_sha256(target) != digest:
            raise ValueError("冻结对照文件身份冲突，未替换原文件")
        output.replace(target)
        replacement = {
            key: value
            for key, value in current.items()
            if key
            not in {
                "observed_path",
                "observed_sha256",
                "validation_batch_key",
                "validation_protocol_path",
                "validation_protocol_sha256",
                "disabled_reason",
            }
        }
        replacement.update(
            id=f"managed-{cell.lower()}-{digest[:16]}",
            control_path=target.relative_to(self.root).as_posix(),
            control_sha256=digest,
            enabled=True,
        )
        document["datasets"] = [
            replacement,
            *[row for row in document["datasets"] if row["id"] != replacement["id"]],
        ]
        # Validate before publication. Old IDs remain resolvable for frozen historical results.
        from backend.app.core.registry import _DatasetRow

        _DatasetRow.model_validate(replacement)
        atomic_write_json(path, document)
        registry.datasets = AssetRegistry(self.root, registry.registry_root).datasets

    async def cancel(self, cell: str) -> None:
        if self.active_cell == cell and (not self.task or self.task.done()):
            raise RuntimeError("任务由另一个服务进程执行，请在发起任务的服务端口取消")
        if self.active_cell == cell and self.task and not self.task.done():
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
            if self.active_cell == cell:
                self.update(cell, status="cancelled", message="已取消，可重试续传已下载的权重")
                if self.lease:
                    self.lease.close()
                self.lease, self.active_cell = None, None

    async def close(self) -> None:
        if self.active_cell and self.task and not self.task.done():
            await self.cancel(self.active_cell)
