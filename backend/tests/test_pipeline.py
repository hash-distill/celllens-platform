import hashlib
import json

from backend.app.core.registry import AssetRegistry
from backend.app.core.storage import RunStore
from backend.app.schemas import CreateRunRequest, RunStatus
from backend.app.services.pipeline import AnalysisPipeline
from backend.app.services.scientific_analysis import AnalysisResult


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeStateEngine:
    def infer(self, request, model, output_path):
        output_path.write_bytes(b"valid-state-output")
        return output_path


class FakeAnalysisService:
    def run(self, run_id, request, model, dataset, predicted_path, output_dir):
        gene_path = output_dir / "gene_deltas.csv"
        gene_path.write_text("gene,predicted_delta\nMYC,1.0\n", encoding="utf-8")
        return AnalysisResult(
            summary={
                "run_id": run_id,
                "status": "completed",
                "stage_progress": 100,
                "cell_line": request.cell_line,
                "perturbation": request.perturbation,
                "coverage": None,
                "top_genes": [
                    {
                        "id": "MYC",
                        "label": "MYC",
                        "predicted_delta": 1.0,
                        "observed_delta": None,
                        "coverage": 1.0,
                        "evidence_level": "supported",
                        "determinant_genes": ["MYC"],
                    }
                ],
                "metabolic_tasks": [],
                "warnings": ["metabolic database unavailable"],
                "error_code": None,
            },
            artifacts=[gene_path],
        )


def test_pipeline_publishes_real_summary_and_artifact_manifest(tmp_path):
    registry_root = tmp_path / "data" / "registry"
    registry_root.mkdir(parents=True)
    checkpoint = tmp_path / "models" / "checkpoint.ckpt"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_bytes(b"checkpoint")
    control = tmp_path / "data" / "control.h5ad"
    control.write_bytes(b"control")
    (registry_root / "models.json").write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "state-test",
                        "cell_line": "K562",
                        "enabled": True,
                        "checkpoint_path": "models/checkpoint.ckpt",
                        "checkpoint_sha256": _sha(checkpoint),
                        "supported_perturbations": ["MYC"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (registry_root / "datasets.json").write_text(
        json.dumps(
            {
                "datasets": [
                    {
                        "id": "dataset-test",
                        "cell_line": "K562",
                        "enabled": True,
                        "control_path": "data/control.h5ad",
                        "control_sha256": _sha(control),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    store = RunStore(f"sqlite+pysqlite:///{(tmp_path / 'runs.db').as_posix()}", create_schema=True)
    derived = tmp_path / "data" / "derived" / "runs"
    pipeline = AnalysisPipeline(
        store,
        AssetRegistry(tmp_path, registry_root),
        FakeStateEngine(),
        FakeAnalysisService(),
        derived,
        worker_id="test-worker",
        lease_seconds=60,
    )
    store.create("run_1", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    pipeline._run_sync("run_1")

    assert store.get("run_1").status == RunStatus.COMPLETED
    summary = json.loads((derived / "run_1" / "summary.json").read_text(encoding="utf-8"))
    assert summary["top_genes"][0]["id"] == "MYC"
    assert {artifact.kind for artifact in store.artifacts("run_1")} >= {
        "state_prediction",
        "summary",
        "manifest",
        "gene_deltas",
    }
    assert not list(derived.glob("run_1.attempt-*.partial"))
