"""Run fresh real MySQL/CUDA/STATE/scCellFie predictions for the three added contexts.

Stop the older application worker before running this check, then restart the app
after it finishes, so one registry version owns these jobs.
"""

import argparse
import json
import time
from pathlib import Path

import anndata as ad
import numpy as np
import scipy.sparse as sp
import torch
from fastapi.testclient import TestClient

from backend.app.core.run_manifest import file_sha256
from backend.app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed", type=int, default=42, help="Use a new seed when deliberately repeating fresh inference"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = root / "reports/context-integration-2026-10-08"
    out.mkdir(parents=True, exist_ok=True)
    assert torch.cuda.is_available(), "Real CUDA inference requires an available GPU"
    proof = {"device": torch.cuda.get_device_name(0), "runs": []}
    with TestClient(create_app()) as client:
        for line in ["RPE1", "Jurkat", "HepG2"]:
            response = client.post(
                "/api/v1/runs",
                json={
                    "cell_line": line,
                    "perturbation": "AAMP",
                    "mode": "online",
                    "n_cells": 64,
                    "seed": args.seed,
                },
            )
            response.raise_for_status()
            created = response.json()
            assert not created["cache_hit"], f"Fresh inference required: {created}"
            run_id = created["run_id"]
            print("fresh CUDA run", line, run_id, flush=True)
            deadline = time.monotonic() + 1200
            last_status = None
            while time.monotonic() < deadline:
                record_response = client.get(f"/api/v1/runs/{run_id}")
                record_response.raise_for_status()
                record = record_response.json()
                if record["status"] != last_status:
                    print(line, record["status"], record["stage_progress"], flush=True)
                    last_status = record["status"]
                if record["status"] in {"completed", "failed"}:
                    break
                time.sleep(2)
            assert record["status"] == "completed", record
            run_root = root / "data/derived/runs" / run_id
            manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
            for name, asset in manifest["outputs"].items():
                assert file_sha256(run_root / name) == asset["sha256"], name
            frame = ad.read_h5ad(run_root / "predicted.h5ad")
            assert set(frame.obs["cell_line"].astype(str)) == {line.lower()}
            selected = frame.obs["gene"].astype(str).str.upper() == "AAMP"
            assert int(selected.sum()) == 64
            matrix = np.asarray(frame.obsm["X_hvg"])[selected]
            assert matrix.shape == (64, 2000) and np.isfinite(matrix).all()
            models = json.loads((root / "data/registry/models.json").read_text())["models"]
            model = next(row for row in models if row["cell_line"] == line)
            panel = (root / model["gene_list_path"]).read_text().splitlines()
            original = sp.csr_matrix(frame[selected, panel].X).toarray()
            input_difference = float(np.abs(matrix - original).mean())
            assert input_difference > 0, "Prediction must differ from its unchanged cloned input"
            endpoints = {}
            for suffix in ["summary", "projection", "genes", "metabolic-tasks", "reactions", "report"]:
                result = client.get(f"/api/v1/runs/{run_id}/{suffix}")
                result.raise_for_status()
                endpoints[suffix] = result.status_code
            projection = client.get(f"/api/v1/runs/{run_id}/projection").json()
            assert projection["population_selection"]["selected_prediction_cells"] == 64
            counts = {
                source: sum(p["source"] == source for p in projection["points"])
                for source in ["control", "predicted", "observed"]
            }
            assert counts == {"control": 1024, "predicted": 64, "observed": 0}, counts
            tasks = client.get(f"/api/v1/runs/{run_id}/metabolic-tasks?scope=all&limit=10000").json()
            assert tasks["total"] > 0 and tasks["reactions_available"]
            trace_task = next(item["id"] for item in tasks["items"] if item["trace_available"])
            trace = client.get(f"/api/v1/runs/{run_id}/task-trace", params={"task_id": trace_task})
            trace.raise_for_status()
            summary = client.get(f"/api/v1/runs/{run_id}/summary").json()
            proof["runs"].append(
                {
                    "cell_line": line,
                    "run_id": run_id,
                    "perturbation": "AAMP",
                    "cache_hit": False,
                    "status": record["status"],
                    "predicted_cells": int(selected.sum()),
                    "prediction_shape": list(matrix.shape),
                    "prediction_slot": "obsm/X_hvg",
                    "mean_abs_difference_from_cloned_input": input_difference,
                    "projection_counts": counts,
                    "model_id": manifest["assets"]["model_id"],
                    "assets": manifest["assets"],
                    "metabolic_tasks": tasks["total"],
                    "coverage": summary["coverage"],
                    "warnings": summary["warnings"],
                    "endpoints": endpoints,
                    "manifest_sha256": file_sha256(run_root / "manifest.json"),
                }
            )
            (out / "real_runs.json").write_text(
                json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print("verified real prediction", line, run_id, flush=True)
    before = json.loads((out / "before-models.json").read_text())["models"]
    after = json.loads((root / "data/registry/models.json").read_text())["models"]
    assert next(row for row in before if row["cell_line"] == "K562") == next(
        row for row in after if row["cell_line"] == "K562"
    )
    for row in json.loads((out / "before-datasets.json").read_text())["datasets"]:
        for path_field, hash_field in [
            ("control_path", "control_sha256"),
            ("observed_path", "observed_sha256"),
        ]:
            assert file_sha256(root / row[path_field]) == row[hash_field], "Existing K562 input changed"
    print("PASS three fresh real predictions; existing K562 assets preserved", flush=True)


if __name__ == "__main__":
    main()
