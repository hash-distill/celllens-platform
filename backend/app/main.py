from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.app.api.catalog import router as catalog_router
from backend.app.api.runs import router as runs_router
from backend.app.config import Settings, get_settings
from backend.app.container import build_container


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    container = build_container(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if resolved.worker_enabled:
            await container.queue.start()
            for run_id in container.store.list_recoverable_run_ids():
                container.store.prepare_recovery(run_id)
                await container.queue.submit(run_id)
        yield
        if resolved.worker_enabled:
            await container.queue.stop()

    application = FastAPI(
        title="CellLens API",
        version="0.1.0",
        description="Traceable STATE and scCellFie orchestration API",
        lifespan=lifespan,
    )
    application.state.container = container

    @application.get(f"{resolved.api_prefix}/health", tags=["system"])
    def health() -> dict[str, str]:
        try:
            container.store.ping()
        except Exception:
            return {"service": "celllens", "status": "degraded", "database": "unavailable"}
        return {"service": "celllens", "status": "ok", "database": "ok"}

    @application.get(f"{resolved.api_prefix}/ready", tags=["system"])
    def ready() -> JSONResponse:
        checks = {
            "database": False,
            "worker": resolved.worker_enabled,
            "gpu": resolved.gpu_available,
        }
        try:
            checks["database"] = container.store.ping()
        except Exception:
            pass
        ready_status = all(checks.values())
        return JSONResponse(
            status_code=200 if ready_status else 503,
            content={"service": "celllens", "ready": ready_status, "checks": checks},
        )

    application.include_router(catalog_router, prefix=resolved.api_prefix)
    application.include_router(runs_router, prefix=resolved.api_prefix)
    return application


app = create_app()
