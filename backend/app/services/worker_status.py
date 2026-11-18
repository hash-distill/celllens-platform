"""Observed process liveness and dependency probes, never configuration-as-health."""

import importlib.util
import shutil
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from backend.app.db.models import WorkerHeartbeatModel


def probe_capabilities(settings, kind: str) -> dict:
    required = ("anndata", "numpy", "pandas", "sklearn", "h5py")
    missing = [name for name in required if importlib.util.find_spec(name) is None]
    result = {
        "cpu_analysis": kind == "cpu" and not missing,
        "missing_dependencies": missing,
        "prediction": False,
    }
    if kind == "gpu":
        # External mode runs CUDA checks in the worker. Embedded development mode
        # may request the same real probe after its queue has actually started.
        try:
            import torch

            cuda = bool(torch.cuda.is_available())
        except (ImportError, RuntimeError, OSError):
            cuda = False
        result.update(cuda_detected=cuda, state_executable=bool(shutil.which(settings.state_executable)))
        result["prediction"] = (
            cuda and result["state_executable"] and settings.worker_enabled and settings.gpu_available
        )
    return result


def heartbeat(store, worker_id: str, kind: str, capabilities: dict) -> None:
    now = datetime.now(UTC)
    with store.session_factory.begin() as session:
        row = session.get(WorkerHeartbeatModel, worker_id)
        if row is None:
            session.add(
                WorkerHeartbeatModel(
                    worker_id=worker_id,
                    kind=kind,
                    capabilities_json=capabilities,
                    heartbeat_at=now,
                    started_at=now,
                )
            )
        else:
            row.kind, row.capabilities_json, row.heartbeat_at = kind, capabilities, now


def workers_status(container) -> dict:
    settings = container.settings
    live = []
    if settings.worker_mode == "external" and settings.deployment_mode != "public":
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.worker_stale_seconds)
        with container.store.session_factory() as session:
            rows = list(
                session.scalars(
                    select(WorkerHeartbeatModel).where(WorkerHeartbeatModel.heartbeat_at >= cutoff)
                )
            )
            live = [
                {
                    "kind": row.kind,
                    "heartbeat_at": row.heartbeat_at.isoformat(),
                    "capabilities": row.capabilities_json,
                }
                for row in rows
            ]
    elif settings.worker_mode == "embedded" and settings.deployment_mode != "public":
        task = container.queue._task
        if settings.worker_enabled and task is not None and not task.done():
            live.append(
                {
                    "kind": "embedded_gpu",
                    "heartbeat_at": None,
                    "source": "live_process_probe",
                    "capabilities": probe_capabilities(settings, "gpu"),
                }
            )
    return {
        "mode": settings.worker_mode,
        "live": live,
        "cpu_available": any(row["capabilities"].get("cpu_analysis") for row in live),
        "prediction_available": settings.worker_enabled
        and any(row["capabilities"].get("prediction") for row in live),
    }


def prediction_ready(container) -> bool:
    try:
        return bool(workers_status(container)["prediction_available"])
    except Exception:
        # An unavailable heartbeat table/database is uncertainty, never evidence
        # that the configured GPU switch represents a running inference worker.
        return False
