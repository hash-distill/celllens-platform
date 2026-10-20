"""Bounded, read-only probes. Never expose connection credentials or host paths."""

import csv
import ctypes
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, text

from backend.app.config import PROJECT_ROOT
from backend.app.db.models import RunModel


def setting_sources(fields: tuple[str, ...]) -> dict[str, str]:
    """Report whether a switch came from the shell or from .env.

    A stray shell variable such as CELLLENS_WORKER_ENABLED=false wins over .env and
    silently disables online inference, so the status page points at the real source.
    """
    sources: dict[str, str] = {}
    for field in fields:
        name = f"CELLLENS_{field.upper()}"
        if name in os.environ:
            sources[field] = "environment"
        elif (PROJECT_ROOT / ".env").is_file():
            sources[field] = "env_file"
        else:
            sources[field] = "default"
    return sources


def os_status() -> dict:
    system, release = platform.system(), platform.release()
    details = {
        "os": system,
        "os_release": release,
        "os_version": platform.version(),
        "os_display_version": None,
    }
    if system != "Windows":
        return details
    try:
        version = sys.getwindowsversion()
        # Windows 11 keeps NT 10.0. Only workstation builds >=22000 are Windows 11;
        # server/domain-controller builds must retain their own OS identity.
        if version.product_type == 1 and version.major == 10:
            details["os_release"] = "11" if version.build >= 22000 else "10"
        details["os_version"] = f"{version.major}.{version.minor}.{version.build}"
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        ) as key:
            try:
                details["os_display_version"] = winreg.QueryValueEx(key, "DisplayVersion")[0]
            except OSError:
                pass
            try:
                revision = winreg.QueryValueEx(key, "UBR")[0]
                details["os_version"] += f".{revision}"
            except OSError:
                pass
    except (AttributeError, OSError):
        pass
    return details


def cpu_model() -> str | None:
    """Read the host's processor name rather than the generic architecture identifier."""
    try:
        if platform.system() == "Windows":
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
            ) as key:
                name = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
                if name:
                    return name
        elif platform.system() == "Linux":
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                label, _, value = line.partition(":")
                if label.strip() in ("model name", "Hardware") and value.strip():
                    return value.strip()
    except (OSError, AttributeError):
        pass
    return platform.processor() or None


def memory_status() -> dict:
    try:
        if os.name == "nt":

            class Memory(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                    (name, ctypes.c_ulonglong)
                    for name in (
                        "total",
                        "available",
                        "page_total",
                        "page_available",
                        "virtual",
                        "virtual_available",
                        "extended",
                    )
                ]

            state = Memory()
            state.length = ctypes.sizeof(state)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
                return {"total_bytes": None, "used_bytes": None}
            total, available = state.total, state.available
        else:
            values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
            total = int(values["MemTotal"].split()[0]) * 1024
            available = int(values["MemAvailable"].split()[0]) * 1024
        return {"total_bytes": total, "used_bytes": total - available}
    except (OSError, KeyError, ValueError, AttributeError):
        return {"total_bytes": None, "used_bytes": None}


def gpu_status() -> dict:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

        def number(value: str):
            try:
                return float(value.strip())
            except ValueError:
                return None

        devices = []
        for row in csv.reader(result.stdout.splitlines()):
            if len(row) != 7:
                continue
            values = [number(value) for value in row[3:]]
            devices.append(
                {
                    "index": row[0].strip(),
                    "name": row[1].strip(),
                    "driver_version": row[2].strip(),
                    "memory_total_bytes": values[0] * 1024**2 if values[0] is not None else None,
                    "memory_used_bytes": values[1] * 1024**2 if values[1] is not None else None,
                    "utilization_percent": values[2],
                    "temperature_c": values[3],
                }
            )
        return {
            "detected": bool(devices),
            "devices": devices,
            "message": None if devices else "未检测到 NVIDIA GPU",
        }
    except (OSError, subprocess.SubprocessError):
        return {
            "detected": False,
            "devices": [],
            "message": "未获取 NVIDIA GPU 信息（设备或 nvidia-smi 不可用）",
        }


def system_status(container) -> dict:
    settings, store = container.settings, container.store
    database = {
        "connected": False,
        "engine": store.engine.dialect.name,
        "version": None,
        "latency_ms": None,
        "pool_size": None,
        "checked_out": None,
    }
    counts = {"online_pending": None}
    started = time.perf_counter()
    try:
        with store.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            database["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
            database["connected"] = True
            query = "SELECT sqlite_version()" if database["engine"] == "sqlite" else "SELECT VERSION()"
            database["version"] = str(connection.execute(text(query)).scalar())
        pool = store.engine.pool
        database["pool_size"] = pool.size() if callable(getattr(pool, "size", None)) else None
        database["checked_out"] = pool.checkedout() if callable(getattr(pool, "checkedout", None)) else None
        with store.session_factory() as session:
            counts["online_pending"] = session.scalar(
                select(func.count())
                .select_from(RunModel)
                .where(RunModel.status.notin_(["completed", "failed"]))
            )
    except Exception:
        # Probe failures belong to the status response, never to a raw database exception.
        pass
    versions = {}
    for package in ("fastapi", "sqlalchemy", "torch", "arc-state", "sccellfie", "anndata"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    try:
        disk = shutil.disk_usage(settings.project_root)
        storage = {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free}
    except OSError:
        storage = {"total_bytes": None, "used_bytes": None, "free_bytes": None}
    gpu = gpu_status()
    gpu["configured"] = settings.gpu_available
    gpu_task = container.queue._task
    workers = {
        "online_enabled": settings.worker_enabled,
        "online_running": gpu_task is not None and not gpu_task.done(),
        **counts,
        "sources": setting_sources(("worker_enabled", "gpu_available")),
    }
    return {
        "service": "celllens",
        "checked_at": datetime.now(UTC).isoformat(),
        "database": database,
        "gpu": gpu,
        "workers": workers,
        "system": {
            **os_status(),
            "architecture": platform.machine(),
            "python": platform.python_version(),
            "cpu_model": cpu_model(),
            "cpu_logical_cores": os.cpu_count(),
            "memory": memory_status(),
            "storage": storage,
        },
        "versions": versions,
    }
