import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.run_manifest import file_sha256
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus
from backend.tests.test_api_runs import _settings, _write_registry


def write_bundle(root: Path, name: str = "MYC") -> Path:
    source = root / "data/demo/K562" / name
    source.mkdir(parents=True)
    summary = {
        "run_id": "template",
        "status": "completed",
        "stage_progress": 100,
        "cell_line": "K562",
        "perturbation": name,
    }
    (source / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (source / "projection.json").write_text(
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
    (source / "manifest.json").write_text(
        json.dumps(
            {"files": {name: file_sha256(source / name) for name in ["summary.json", "projection.json"]}}
        ),
        encoding="utf-8",
    )
    return source


def test_demo_catalog_only_lists_verified_combinations(tmp_path):
    _write_registry(tmp_path)
    write_bundle(tmp_path)
    invalid = write_bundle(tmp_path, "AAAS")
    (invalid / "summary.json").write_text("{}", encoding="utf-8")
    app = create_app(_settings(tmp_path, allow_synthetic_results=True))
    with TestClient(app) as client:
        response = client.get("/api/v1/catalog/perturbations?cell_line=K562&mode=precomputed")
        assert response.json()["items"] == ["MYC"]
        contexts = client.get("/api/v1/catalog/contexts").json()
        assert contexts[0]["precomputed_ready"] is True
        (tmp_path / "data/demo/K562/MYC/summary.json").write_text("{}", encoding="utf-8")
        assert client.get("/api/v1/catalog/contexts").json()[0]["precomputed_ready"] is False


def test_spa_routes_and_api_404_are_separate(tmp_path):
    _write_registry(tmp_path)
    dist = tmp_path / "frontend/dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>CellLens SPA</html>", encoding="utf-8")
    (dist / "assets/main.js").write_text("console.log('ok')", encoding="utf-8")
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        for url in ("/", "/workbench", "/records", "/compare", "/demo", "/about", "/runs/run_example"):
            assert "CellLens SPA" in client.get(url).text
        assert client.get("/assets/main.js").status_code == 200
        assert client.get("/assets/missing.js").status_code == 404
        assert client.get("/api/v1/unknown").status_code == 404
        assert client.get("/api/v1/unknown").headers["content-type"].startswith("application/json")


def test_favicon_png_and_default_ico_request_serve_the_same_icon(tmp_path):
    _write_registry(tmp_path)
    dist = tmp_path / "frontend/dist"
    dist.mkdir(parents=True)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        assert client.get("/favicon.png").status_code == 404
        icon = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="
        )
        (dist / "favicon.png").write_bytes(icon)
        for url in ("/favicon.png", "/favicon.ico"):
            response = client.get(url)
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            assert response.headers["cache-control"] == "no-cache"
            assert response.content == icon


def completed_run(app, root):
    app.state.container.store.create("run_fixture", CreateRunRequest(cell_line="K562", perturbation="MYC"))
    app.state.container.store.transition("run_fixture", RunStatus.COMPLETED, 100)
    path = root / "data/derived/runs/run_fixture"
    path.mkdir(parents=True)
    return path


def test_provenance_uses_historical_manifest_and_filters_private_fields(tmp_path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        path = completed_run(app, tmp_path)
        (path / "manifest.json").write_text(
            json.dumps(
                {
                    "assets": {
                        "model_id": "historical-model",
                        "checkpoint_sha256": "a" * 64,
                        "private_path": "D:/secret",
                    },
                    "code_sha256": "b" * 64,
                    "worker_id": "private-host",
                    "outputs": {"summary.json": {"sha256": "c" * 64, "size_bytes": 123}},
                }
            ),
            encoding="utf-8",
        )
        response = client.get("/api/v1/runs/run_fixture/provenance")
        assert response.status_code == 200
        document = response.json()
        assert document["assets"]["model_id"] == "historical-model"
        assert document["source_type"] == "online"
        assert "private-host" not in response.text and "D:/secret" not in response.text
        assert document["manifest_sha256"] == file_sha256(path / "manifest.json")


def test_validation_does_not_fabricate_missing_metrics(tmp_path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        path = completed_run(app, tmp_path)
        response = client.get("/api/v1/runs/run_fixture/validation")
        assert response.status_code == 404
        metrics = {
            "spearman": None,
            "mae": 0.2,
            "direction_agreement": 0.5,
            "top_k_overlap": 0.3,
            "valid_task_count": 12,
            "excluded_task_count": 2,
        }
        (path / "validation_metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
        response = client.get("/api/v1/runs/run_fixture/validation")
        assert response.status_code == 200
        assert response.json()["metrics"] == metrics
        assert response.json()["protocol_status"] == "unconfirmed"


def test_all_task_endpoint_uses_full_scores_and_run_coverage(tmp_path):
    _write_registry(tmp_path)
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        path = completed_run(app, tmp_path)
        columns = [f"task_{index}" for index in range(23)]
        (path / "metabolic_task_scores.csv").write_text(
            "cell,"
            + ",".join(columns)
            + ",source\n"
            + "c,"
            + ",".join(["1"] * 23)
            + ",control\n"
            + "p,"
            + ",".join(["2"] * 23)
            + ",predicted\n",
            encoding="utf-8",
        )
        (path / "metabolic_coverage.csv").write_text(
            "task,gene_fraction,evidence_level,missing_genes\n"
            + "\n".join(f"{name},0.5,insufficient,MYC" for name in columns),
            encoding="utf-8",
        )
        response = client.get("/api/v1/runs/run_fixture/metabolic-tasks?scope=all")
        assert response.status_code == 200
        document = response.json()
        assert document["scope"] == "all" and document["total"] == 23
        assert len(document["items"]) == 23
        assert document["items"][0]["predicted_delta"] == 1
        assert document["items"][0]["coverage"] == 0.5
        assert document["items"][0]["observed_delta"] is None
