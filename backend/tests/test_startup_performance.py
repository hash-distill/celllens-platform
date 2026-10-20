"""Startup optimizations must not weaken inference-time provenance checks."""

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core import registry as registry_module
from backend.app.main import create_app
from backend.tests.test_api_modes import settings, write_registry


def test_context_readiness_reuses_unchanged_asset_hashes_but_execution_rechecks(tmp_path, monkeypatch):
    write_registry(tmp_path, valid=True)
    original = registry_module.file_sha256
    hashed = []

    def measured(path):
        hashed.append(path)
        return original(path)

    monkeypatch.setattr(registry_module, "file_sha256", measured)
    app = create_app(settings(tmp_path, gpu_available=True, worker_enabled=True))
    with TestClient(app) as client:
        for _ in range(3):
            assert client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]
        assert len(hashed) == 2, "Readiness repeatedly reread the same checkpoint and control"
        model = app.state.container.registry.model_for("K562")
        for _ in range(2):
            app.state.container.registry.verify_entry(model, "checkpoint_path", "checkpoint_sha256")
        assert len(hashed) == 4, "Execution verification must perform a fresh digest"


def test_changed_or_removed_asset_immediately_invalidates_readiness(tmp_path):
    write_registry(tmp_path, valid=True)
    app = create_app(settings(tmp_path, gpu_available=True, worker_enabled=True))
    checkpoint = tmp_path / "models/m/checkpoints/final.ckpt"
    with TestClient(app) as client:
        assert client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]
        checkpoint.write_bytes(b"a changed checkpoint")
        assert not client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]
        checkpoint.write_bytes(b"checkpoint")
        assert client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]
        checkpoint.unlink()
        assert not client.get("/api/v1/catalog/contexts").json()[0]["online_ready"]


def test_api_import_does_not_initialize_statistical_diagnostics():
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", "import sys; import backend.app.main; "
         "assert 'scipy.stats' not in sys.modules"],
        cwd=root,
        env={**os.environ, "CELLLENS_WORKER_ENABLED": "false"},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
