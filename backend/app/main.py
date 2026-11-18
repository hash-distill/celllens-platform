from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

from backend.app.access import WorkspaceAccessMiddleware
from backend.app.access import router as access_router
from backend.app.api.catalog import router as catalog_router
from backend.app.api.comparisons import router as comparisons_router
from backend.app.api.coverage import router as coverage_router
from backend.app.api.data_catalog import router as data_catalog_router
from backend.app.api.datasets import router as datasets_router
from backend.app.api.experiments import router as experiments_router
from backend.app.api.exports import router as exports_router
from backend.app.api.figures import router as figures_router
from backend.app.api.measured import router as measured_router
from backend.app.api.operations import router as operations_router
from backend.app.api.research import router as research_router
from backend.app.api.resources import router as resources_router
from backend.app.api.runs import router as runs_router
from backend.app.api.uploads import router as uploads_router
from backend.app.assistant import AssistantService
from backend.app.assistant import router as assistant_router
from backend.app.assistant_middleware import AssistantRequestMiddleware
from backend.app.config import Settings, get_settings
from backend.app.container import build_container
from backend.app.coverage_middleware import CoverageCompressionMiddleware
from backend.app.services.measured_jobs import MeasuredJobs
from backend.app.services.resource_downloads import ResourceManager
from backend.app.services.system_status import system_status
from backend.app.services.worker_status import workers_status


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    container = build_container(resolved)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if resolved.worker_mode == "embedded":
            application.state.measured.recover()
        if resolved.worker_enabled and resolved.worker_mode == "embedded":
            await container.queue.start()
            for run_id in container.store.list_recoverable_run_ids():
                container.store.prepare_recovery(run_id)
                await container.queue.submit(run_id)
        yield
        await application.state.measured.close()
        await application.state.resources.close()
        if resolved.worker_enabled and resolved.worker_mode == "embedded":
            await container.queue.stop()

    application = FastAPI(
        title="CellLens API",
        version="0.1.0",
        description="Traceable STATE and scCellFie orchestration API",
        lifespan=lifespan,
    )
    application.state.container = container
    application.state.assistant = AssistantService(resolved)
    application.state.resources = ResourceManager(container)
    application.state.measured = MeasuredJobs(container)
    application.add_middleware(AssistantRequestMiddleware, api_prefix=resolved.api_prefix)
    application.add_middleware(CoverageCompressionMiddleware, api_prefix=resolved.api_prefix)
    application.add_middleware(WorkspaceAccessMiddleware, settings=resolved)

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
        checks = {"database": False}
        workers = {
            "mode": resolved.worker_mode,
            "live": [],
            "cpu_available": False,
            "prediction_available": False,
        }
        try:
            checks["database"] = container.store.ping()
            workers = workers_status(container)
        except Exception:
            pass
        # Viewing completed research remains ready without any GPU/worker.
        ready_status = checks["database"]
        return JSONResponse(
            status_code=200 if ready_status else 503,
            content={
                "service": "celllens",
                "ready": ready_status,
                "checks": checks,
                "capabilities": {
                    "result_browsing": ready_status,
                    "cpu_analysis": ready_status and workers["cpu_available"],
                    "prediction": ready_status and workers["prediction_available"],
                },
                "workers": workers,
            },
        )

    @application.get(f"{resolved.api_prefix}/system-status", tags=["system"])
    def environment_status() -> JSONResponse:
        return JSONResponse(content=system_status(container), headers={"Cache-Control": "no-store"})

    application.include_router(experiments_router, prefix=resolved.api_prefix)
    application.include_router(catalog_router, prefix=resolved.api_prefix)
    application.include_router(data_catalog_router, prefix=resolved.api_prefix)
    application.include_router(datasets_router, prefix=resolved.api_prefix)
    application.include_router(figures_router, prefix=resolved.api_prefix)
    application.include_router(measured_router, prefix=resolved.api_prefix)
    application.include_router(coverage_router, prefix=resolved.api_prefix)
    application.include_router(runs_router, prefix=resolved.api_prefix)
    application.include_router(resources_router, prefix=resolved.api_prefix)
    application.include_router(comparisons_router, prefix=resolved.api_prefix)
    application.include_router(exports_router, prefix=resolved.api_prefix)
    application.include_router(assistant_router, prefix=resolved.api_prefix)
    application.include_router(access_router, prefix=resolved.api_prefix)
    application.include_router(research_router, prefix=resolved.api_prefix)
    application.include_router(uploads_router, prefix=resolved.api_prefix)
    application.include_router(operations_router, prefix=resolved.api_prefix)

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
        return FileResponse(
            path,
            media_type="image/webp" if path.suffix.lower() == ".webp" else None,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    @application.get("/", include_in_schema=False)
    @application.get("/research", include_in_schema=False)
    @application.get("/workbench", include_in_schema=False)
    @application.get("/data-catalog", include_in_schema=False)
    @application.get("/measured", include_in_schema=False)
    @application.get("/measured/{analysis_id}", include_in_schema=False)
    @application.get("/records", include_in_schema=False)
    @application.get("/compare", include_in_schema=False)
    @application.get("/demo", include_in_schema=False)
    @application.get("/about", include_in_schema=False)
    @application.get("/settings", include_in_schema=False)
    @application.get("/status", include_in_schema=False)
    @application.get("/coverage", include_in_schema=False)
    @application.get("/methods", include_in_schema=False)
    @application.get("/methods/models", include_in_schema=False)
    @application.get("/methods/data", include_in_schema=False)
    @application.get("/methods/backgrounds", include_in_schema=False)
    @application.get("/methods/coverage", include_in_schema=False)
    @application.get("/runs/{run_id}", include_in_schema=False)
    @application.get("/datasets", include_in_schema=False)
    @application.get("/figures/{record_kind}/{record_id}", include_in_schema=False)
    def frontend_page(run_id: str | None = None, analysis_id: str | None = None) -> FileResponse:
        index = dist / "index.html"
        if not index.is_file():
            raise HTTPException(
                status_code=503, detail="Build the frontend first: npm --prefix frontend run build"
            )
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return application


app = create_app()
