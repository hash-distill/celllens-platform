import asyncio
import html
import logging
import shutil
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from backend.app.core.cache import code_fingerprint
from backend.app.core.errors import CellLensError, JobAlreadyClaimedError
from backend.app.core.registry import AssetRegistry
from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.core.storage import RunStore
from backend.app.engines.state_engine import StateCliEngine, StateRunInput
from backend.app.schemas import RunStatus, RunSummary
from backend.app.services.scientific_analysis import ScientificAnalysisService

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    def __init__(
        self,
        store: RunStore,
        registry: AssetRegistry,
        state_engine: StateCliEngine,
        analysis_service: ScientificAnalysisService,
        derived_root: Path,
        *,
        worker_id: str,
        lease_seconds: int,
    ):
        self.store = store
        self.registry = registry
        self.state_engine = state_engine
        self.analysis_service = analysis_service
        self.derived_root = derived_root
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds

    async def run(self, run_id: str) -> None:
        await asyncio.to_thread(self._run_sync, run_id)

    def _run_sync(self, run_id: str) -> None:
        with self.store.named_lock("celllens:a6000", timeout_seconds=self.lease_seconds):
            self._run_with_gpu_lock(run_id)

    def _run_with_gpu_lock(self, run_id: str) -> None:
        try:
            attempt = self.store.start_attempt(
                run_id,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
        except JobAlreadyClaimedError:
            return
        record = self.store.get(run_id)
        request = record.request
        partial = self.derived_root / f"{run_id}.attempt-{attempt.attempt_no}.partial"
        final = self.derived_root / run_id
        if partial.exists():
            shutil.rmtree(partial)
        partial.mkdir(parents=True, exist_ok=False)
        warnings: list[str] = []
        try:
            model = self.registry.model_for(request.cell_line)
            dataset = self.registry.dataset_for(request.cell_line)
            checkpoint_hash = self.registry.verify_entry(model, "checkpoint_path", "checkpoint_sha256")
            control_hash = self.registry.verify_entry(dataset, "control_path", "control_sha256")
            gene_hash = None
            if model.payload.get("gene_list_path"):
                gene_hash = self.registry.verify_entry(model, "gene_list_path", "gene_list_sha256")
            config_hash = None
            if model.payload.get("config_path"):
                config_hash = self.registry.verify_entry(model, "config_path", "config_sha256")
            split_hash = None
            if dataset.payload.get("split_path"):
                split_hash = self.registry.verify_entry(dataset, "split_path", "split_sha256")
            observed_hash = None
            if request.mode == "validation":
                observed_hash = self.registry.verify_entry(dataset, "observed_path", "observed_sha256")

            with _lease_heartbeat(self.store, attempt.id, self.lease_seconds):
                self.store.transition(run_id, RunStatus.STATE_RUNNING, 15, message="STATE inference started")
                predicted_path = partial / "predicted.h5ad"
                self.state_engine.infer(
                    StateRunInput(
                        cell_line=request.cell_line,
                        perturbation=request.perturbation,
                        control_path=dataset.path("control_path"),
                        n_cells=request.n_cells,
                        seed=request.seed,
                    ),
                    model,
                    predicted_path,
                )
                self.store.transition(run_id, RunStatus.ADAPTING, 45, message="expression sources aligned")
                self.store.transition(
                    run_id, RunStatus.METABOLIC_RUNNING, 65, message="scientific analysis started"
                )
                analysis = self.analysis_service.run(
                    run_id,
                    request,
                    model,
                    dataset,
                    predicted_path,
                    partial,
                )
                validated_summary = RunSummary.model_validate(analysis.summary)
            warnings.extend(analysis.summary.get("warnings", []))
            self.store.transition(run_id, RunStatus.VALIDATING, 85, warnings=warnings)
            atomic_write_json(partial / "summary.json", validated_summary.model_dump(mode="json"))
            report_path = partial / "report.html"
            report_path.write_text(_render_report(validated_summary), encoding="utf-8")
            manifest = {
                "request": request.model_dump(mode="json"),
                "attempt": attempt.attempt_no,
                "worker_id": self.worker_id,
                "cache_key": self.store.cache_key(run_id),
                "code_sha256": code_fingerprint(self.registry.project_root),
                "assets": {
                    "model_id": model.payload.get("id"),
                    "checkpoint_sha256": checkpoint_hash,
                    "gene_list_sha256": gene_hash,
                    "config_sha256": config_hash,
                    "dataset_id": dataset.payload.get("id"),
                    "control_sha256": control_hash,
                    "observed_sha256": observed_hash,
                    "split_sha256": split_hash,
                },
                "outputs": {},
                "warnings": warnings,
            }
            for path in [predicted_path, *analysis.artifacts, partial / "summary.json", report_path]:
                manifest["outputs"][path.name] = {
                    "sha256": file_sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            atomic_write_json(partial / "manifest.json", manifest)
            if final.exists():
                raise FileExistsError(f"Immutable run directory already exists: {final}")
            partial.replace(final)
            for path in final.iterdir():
                if path.is_file():
                    self.store.register_artifact(
                        run_id,
                        _artifact_kind(path),
                        f"{run_id}/{path.name}",
                        file_sha256(path),
                        path.stat().st_size,
                        _mime_type(path),
                    )
            self.store.transition(run_id, RunStatus.COMPLETED, 100, warnings=warnings)
            if cache_key := self.store.cache_key(run_id):
                self.store.put_cache(cache_key, run_id)
            self.store.finish_attempt(attempt.id, succeeded=True)
        except Exception as exc:
            error_code = exc.code if isinstance(exc, CellLensError) else "PIPELINE_FAILED"
            current = self.store.get(run_id)
            if current.status not in {RunStatus.COMPLETED, RunStatus.FAILED}:
                self.store.transition(
                    run_id,
                    RunStatus.FAILED,
                    current.stage_progress,
                    warnings=warnings,
                    error_code=error_code,
                    error_message=str(exc),
                )
            failure_root = partial if partial.exists() else final
            atomic_write_json(failure_root / "failure.json", {"error_code": error_code, "message": str(exc)})
            self.store.finish_attempt(attempt.id, succeeded=False, error_code=error_code)
            raise

    def allocate_run_id(self) -> str:
        return f"run_{uuid.uuid4().hex[:16]}"

    def clear_partial(self, run_id: str) -> None:
        for path in self.derived_root.glob(f"{run_id}.attempt-*.partial"):
            if path.parent == self.derived_root:
                shutil.rmtree(path, ignore_errors=True)


def _artifact_kind(path: Path) -> str:
    mapping = {
        "predicted.h5ad": "state_prediction",
        "summary.json": "summary",
        "manifest.json": "manifest",
        "gene_deltas.csv": "gene_deltas",
        "metabolic_coverage.csv": "metabolic_coverage",
        "metabolic_task_scores.csv": "metabolic_tasks",
        "reaction_scores.csv": "reaction_scores",
        "validation_metrics.json": "validation_metrics",
        "projection.json": "projection",
        "report.html": "report",
    }
    return mapping.get(path.name, path.stem[:64])


def _mime_type(path: Path) -> str:
    return {
        ".json": "application/json",
        ".csv": "text/csv",
        ".h5ad": "application/x-hdf5",
        ".log": "text/plain",
        ".tsv": "text/tab-separated-values",
        ".html": "text/html",
    }.get(path.suffix.lower(), "application/octet-stream")


def _render_report(summary: RunSummary) -> str:
    top_genes = "".join(
        f"<li>{html.escape(item.label)}: {item.predicted_delta:.6g}</li>" for item in summary.top_genes[:20]
    )
    tasks = "".join(
        f"<li>{html.escape(item.label)}: {item.predicted_delta:.6g} ({item.evidence_level})</li>"
        for item in summary.metabolic_tasks[:20]
    )
    warnings = "".join(f"<li>{html.escape(item)}</li>" for item in summary.warnings)
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'>"
        f"<title>CellLens {html.escape(summary.run_id)}</title><body>"
        f"<h1>CellLens 分析报告</h1><p>运行：{html.escape(summary.run_id)}</p>"
        f"<p>细胞系：{html.escape(summary.cell_line)}；扰动：{html.escape(summary.perturbation)}</p>"
        f"<h2>主要基因变化</h2><ol>{top_genes}</ol>"
        f"<h2>代谢任务</h2><ol>{tasks}</ol><h2>警告</h2><ul>{warnings}</ul>"
        "</body></html>"
    )


@contextmanager
def _lease_heartbeat(store: RunStore, attempt_id: int, lease_seconds: int) -> Iterator[None]:
    stopped = threading.Event()
    interval = max(1.0, min(60.0, lease_seconds / 3))

    def renew() -> None:
        while not stopped.wait(interval):
            try:
                store.heartbeat(attempt_id, lease_seconds)
            except Exception:
                logger.exception("Unable to renew lease for attempt %s", attempt_id)

    thread = threading.Thread(target=renew, name=f"celllens-lease-{attempt_id}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=interval + 1)
