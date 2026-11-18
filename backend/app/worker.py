"""Persistent database-polling worker: python -m backend.app.worker --kind cpu."""

import argparse
import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys
from uuid import uuid4

from backend.app.config import get_settings
from backend.app.container import build_container
from backend.app.services.measured_jobs import MeasuredJobs
from backend.app.services.worker_status import heartbeat, probe_capabilities

logger = logging.getLogger(__name__)


async def run_prediction(container, run_id):
    environment = os.environ.copy()
    environment.update(
        CELLLENS_PROJECT_ROOT=str(container.settings.project_root),
        CELLLENS_DATABASE_URL=container.settings.database_url,
        CELLLENS_WORKER_ID=container.settings.worker_id,
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "backend.app.prediction_worker",
        "--run-id",
        run_id,
        "--parent-pid",
        str(os.getpid()),
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    try:
        async with asyncio.timeout(7200):
            while process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=1)
                except TimeoutError:
                    if container.store.get(run_id).error_code == "RUN_CANCELLED":
                        return
            if process.returncode:
                logger.error("Prediction attempt process exited with code %s", process.returncode)
    finally:
        if process.returncode is None:
            if os.name == "nt":
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                await killer.wait()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            await process.wait()


async def serve(container, kind: str, *, once: bool = False):
    if container.settings.deployment_mode == "public" or container.settings.worker_mode != "external":
        raise RuntimeError("Standalone workers require external mode and a local/private deployment")
    settings = container.settings
    capabilities = await asyncio.to_thread(probe_capabilities, settings, kind)
    if not capabilities.get("cpu_analysis" if kind == "cpu" else "prediction"):
        raise RuntimeError(f"{kind} worker dependencies/hardware unavailable: {capabilities}")
    measured = MeasuredJobs(container)
    stop = asyncio.Event()

    async def renew():
        while not stop.is_set():
            try:
                await asyncio.to_thread(heartbeat, container.store, settings.worker_id, kind, capabilities)
            except Exception:
                logger.exception("Worker heartbeat failed; capability expires until the database recovers")
            try:
                await asyncio.wait_for(stop.wait(), timeout=settings.worker_heartbeat_seconds)
            except TimeoutError:
                pass

    pulse = asyncio.create_task(renew())
    try:
        while True:
            try:
                if kind == "cpu":
                    worked = await measured.run_once()
                else:
                    candidates = container.store.list_recoverable_run_ids()
                    worked = bool(candidates)
                    if candidates:
                        run_id = candidates[0]
                        container.store.prepare_recovery(run_id)
                        await run_prediction(container, run_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker cycle failed; durable queue will be polled again")
                worked = False
            if once:
                return
            if not worked:
                await asyncio.sleep(settings.worker_poll_seconds)
    finally:
        stop.set()
        await pulse
        await measured.close()
        # Removal is deliberate shutdown, while crashes age out by heartbeat.
        from backend.app.db.models import WorkerHeartbeatModel

        with container.store.session_factory.begin() as session:
            row = session.get(WorkerHeartbeatModel, settings.worker_id)
            if row:
                session.delete(row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--once", action="store_true", help="Process at most one job, then exit")
    args = parser.parse_args()
    settings = get_settings().model_copy(
        update={"worker_id": f"{socket.gethostname()}:{os.getpid()}:{args.kind}:{uuid4().hex[:8]}"}
    )
    logging.basicConfig(level=settings.log_level)
    try:
        asyncio.run(serve(build_container(settings), args.kind, once=args.once))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
