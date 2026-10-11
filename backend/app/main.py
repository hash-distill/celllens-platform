from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from backend.app.api.catalog import router as catalog_router
from backend.app.api.runs import router as runs_router
from backend.app.assistant import AssistantService
from backend.app.assistant import router as assistant_router
from backend.app.config import Settings, get_settings
from backend.app.container import build_container
from backend.app.user_data.api import router as user_data_router
from backend.app.user_data.middleware import UploadLimitMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    container = build_container(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if resolved.data_worker_enabled:
            await container.data_worker.start()
        if resolved.worker_enabled:
            await container.queue.start()
            for run_id in container.store.list_recoverable_run_ids():
                container.store.prepare_recovery(run_id)
                await container.queue.submit(run_id)
        yield
        if resolved.worker_enabled:
            await container.queue.stop()
        if resolved.data_worker_enabled:
            await container.data_worker.stop()

    application = FastAPI(
        title="CellLens API",
        version="0.1.0",
        description="Traceable STATE and scCellFie orchestration API",
        lifespan=lifespan,
    )
    application.state.container = container
    application.state.assistant = AssistantService(resolved)
    application.add_middleware(UploadLimitMiddleware, settings=resolved)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.url.path.startswith(resolved.api_prefix + "/assistant/"):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": {
                        "code": "INVALID_ASSISTANT_REQUEST",
                        "message": "请检查模型地址、模型名称、API Key 和摘要参数",
                    }
                },
                headers={"Cache-Control": "no-store"},
            )
        return await request_validation_exception_handler(request, exc)

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
    application.include_router(user_data_router, prefix=resolved.api_prefix)
    application.include_router(assistant_router, prefix=resolved.api_prefix)

    # Register after API routes; only known SPA paths receive the HTML fallback.
    dist = (resolved.project_root / "frontend" / "dist").resolve()

    @application.get("/favicon.png", include_in_schema=False)
    @application.get("/favicon.ico", include_in_schema=False)
    def frontend_icon() -> FileResponse:
        path = dist / "favicon.png"
        if not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @application.get("/assets/{asset_path:path}", include_in_schema=False)
    def frontend_asset(asset_path: str) -> FileResponse:
        path = (dist / "assets" / asset_path).resolve()
        if not path.is_relative_to(dist / "assets") or not path.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @application.get("/", include_in_schema=False)
    @application.get("/workbench", include_in_schema=False)
    @application.get("/records", include_in_schema=False)
    @application.get("/compare", include_in_schema=False)
    @application.get("/demo", include_in_schema=False)
    @application.get("/about", include_in_schema=False)
    @application.get("/login", include_in_schema=False)
    @application.get("/datasets", include_in_schema=False)
    @application.get("/settings", include_in_schema=False)
    @application.get("/analyses/{analysis_id}", include_in_schema=False)
    @application.get("/runs/{run_id}", include_in_schema=False)
    def frontend_page(run_id: str | None = None) -> FileResponse:
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(
                status_code=503, detail="Build the frontend first: npm --prefix frontend run build"
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return application


app = create_app()
