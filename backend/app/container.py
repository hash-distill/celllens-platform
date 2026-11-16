from dataclasses import dataclass

from backend.app.config import Settings
from backend.app.core.job_queue import SingleGpuJobQueue
from backend.app.core.registry import AssetRegistry
from backend.app.core.storage import RunStore
from backend.app.engines.state_engine import StateCliEngine
from backend.app.services.pipeline import AnalysisPipeline
from backend.app.services.scientific_analysis import ScientificAnalysisService


@dataclass
class AppContainer:
    settings: Settings
    registry: AssetRegistry
    store: RunStore
    pipeline: AnalysisPipeline
    queue: SingleGpuJobQueue


def build_container(settings: Settings) -> AppContainer:
    from backend.app.db import research_models  # noqa: F401

    registry = AssetRegistry(settings.project_root, settings.registry_root)
    store = RunStore(settings.database_url, create_schema=settings.create_database_schema)
    pipeline = AnalysisPipeline(
        store=store,
        registry=registry,
        state_engine=StateCliEngine(
            settings.state_executable,
            device="cuda" if settings.gpu_available else "cpu",
        ),
        analysis_service=ScientificAnalysisService(
            settings.sccellfie_database_root,
            max_projection_points=settings.max_projection_points,
            gene_identity_root=(
                settings.gene_identity_root if settings.gene_identity_root.exists() else None
            ),
        ),
        derived_root=settings.derived_root,
        worker_id=settings.worker_id,
        lease_seconds=settings.job_lease_seconds,
    )
    queue = SingleGpuJobQueue(pipeline.run, embedded=settings.worker_mode == "embedded")
    return AppContainer(settings, registry, store, pipeline, queue)
