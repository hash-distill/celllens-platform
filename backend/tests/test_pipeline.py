import hashlib
import json

import pytest

from backend.app.core.errors import ScientificContractError
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
    def __init__(self, omit_projection=False):
        self.omit_projection = omit_projection

    def run(self, run_id, request, model, dataset, predicted_path, output_dir):
        gene_path = output_dir / "gene_deltas.csv"
        gene_path.write_text("gene,predicted_delta\nMYC,1.0\n", encoding="utf-8")
        projection_path = output_dir / "projection.json"
        artifacts = [gene_path]
        if not self.omit_projection:
            projection_path.write_text(
                json.dumps(
                    {
                        "method": "seeded-random-projection",
                        "seed": 42,
                        "points": [
                            {"x": 0.1, "y": 0.2, "source": "control", "cell_index": 0},
                            {"x": 0.3, "y": 0.4, "source": "predicted", "cell_index": 0},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            artifacts.append(projection_path)
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
            artifacts=artifacts,
        )


@pytest.mark.parametrize("omit_projection", [False, True])
@pytest.mark.parametrize("figure_failure", [False, True])
def test_pipeline_publishes_real_summary_and_artifact_manifest(
    tmp_path, omit_projection, figure_failure, monkeypatch
):
    preparation = []

    def prepare(container, run_id, *, source_root):
        assert container.store.get(run_id).status == RunStatus.VALIDATING
        assert container.store.get(run_id).stage_progress == 85
        assert source_root.name.endswith(".partial")
        assert (source_root / "manifest.json").is_file()
        assert not (container.settings.derived_root / run_id).exists()
        preparation.append(run_id)
        if figure_failure:
            raise RuntimeError("figure preparation failed")
        (source_root / "cell_state").mkdir()
        (source_root / "cell_state" / "prepared.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("backend.app.services.pipeline.prepare_cell_state_artifacts", prepare)
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
        FakeAnalysisService(omit_projection),
        derived,
        worker_id="test-worker",
        lease_seconds=60,
    )
    store.create("run_1", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    if omit_projection:
        with pytest.raises(ScientificContractError, match="Required single-cell projection"):
            pipeline._run_sync("run_1")
        assert store.get("run_1").status == RunStatus.FAILED
        assert store.get("run_1").error_code == "SCIENTIFIC_CONTRACT_ERROR"
        assert not (derived / "run_1").exists()
        return
    # A formal expression analysis requires prepared figures before completion.
    original_run = pipeline.analysis_service.run

    def formal_run(*args):
        result = original_run(*args)
        contract = args[-1] / "expression_contract.json"
        contract.write_text('{"analysis_version":"expression-cp10k-v2"}', encoding="utf-8")
        result.artifacts.append(contract)
        return result

    monkeypatch.setattr(pipeline.analysis_service, "run", formal_run)
    if figure_failure:
        with pytest.raises(RuntimeError, match="figure preparation failed"):
            pipeline._run_sync("run_1")
        assert store.get("run_1").status == RunStatus.FAILED
        assert preparation == ["run_1"]
        return
    pipeline._run_sync("run_1")

    assert store.get("run_1").status == RunStatus.COMPLETED
    assert preparation == ["run_1"]
    summary = json.loads((derived / "run_1" / "summary.json").read_text(encoding="utf-8"))
    assert summary["top_genes"][0]["id"] == "MYC"
    assert {artifact.kind for artifact in store.artifacts("run_1")} >= {
        "state_prediction",
        "summary",
        "manifest",
        "gene_deltas",
        "projection",
        "cell_state_preparation",
    }
    assert not list(derived.glob("run_1.attempt-*.partial"))
