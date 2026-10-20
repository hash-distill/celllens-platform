import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.config import Settings
from backend.app.db.models import RunModel
from backend.app.main import create_app
from backend.app.schemas import CreateRunRequest, RunStatus
from backend.app.services.system_status import gpu_status, os_status
from scripts.clear_experiment_records import clear_records


@pytest.fixture
def app(tmp_path):
    registry = tmp_path / "data/registry"
    registry.mkdir(parents=True)
    for filename, key in (("models.json", "models"), ("datasets.json", "datasets")):
        (registry / filename).write_text(json.dumps({key: []}))
    return create_app(
        Settings(
            _env_file=None,
            project_root=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'records.db'}",
            create_database_schema=True,
            worker_enabled=False,
        )
    )


@pytest.fixture
def seeded(app):
    container = app.state.container
    for index, mode in enumerate(("online", "online", "online", "precomputed", "validation")):
        container.store.create(
            f"run_{index}",
            CreateRunRequest(
                cell_line="K562",
                perturbation=("MYC", "ALDOA", "AAMP", "MYC", "MYC")[index],
                mode=mode,
                n_cells=64,
                seed=42,
            ),
        )
        with container.store.session_factory.begin() as session:
            row = session.get(RunModel, f"run_{index}")
            row.created_at = datetime(2030, 1, 1) + timedelta(seconds=index)
    container.store.transition("run_0", RunStatus.COMPLETED, 100)
    container.store.transition("run_2", RunStatus.FAILED, 0)
    # Pre-existing tables remain untouched and do not appear in current history.
    with container.store.engine.begin() as connection:
        connection.execute(text("CREATE TABLE preserved_records (id INTEGER PRIMARY KEY, value TEXT)"))
        connection.execute(text("INSERT INTO preserved_records VALUES (1, 'original')"))
    return container


def test_history_paginates_and_filters_online_experiments(app, seeded):
    client = TestClient(app)
    result = client.get("/api/v1/experiments?limit=2").json()
    assert result["total"] == 3
    assert [row["id"] for row in result["items"]] == ["run_2", "run_1"]
    second = client.get("/api/v1/experiments?limit=2&offset=2").json()
    assert [row["id"] for row in second["items"]] == ["run_0"]
    assert client.get("/api/v1/experiments?status=active").json()["items"][0]["id"] == "run_1"
    assert client.get("/api/v1/experiments?status=completed").json()["total"] == 1
    assert client.get("/api/v1/experiments?q=aldoa").json()["total"] == 1
    assert client.get("/api/v1/experiments?q=%25").json()["total"] == 0
    assert client.get("/api/v1/experiments?source=online").json()["total"] == 3
    for source in ("upload", "precomputed", "validation"):
        assert client.get("/api/v1/experiments?source=" + source).status_code == 422


def test_clear_requires_inactive_jobs_and_preserves_files_and_unrelated_rows(app, seeded, tmp_path):
    backup = tmp_path / "backup.json"
    with pytest.raises(RuntimeError, match="active"):
        clear_records(seeded.store, backup)
    assert not backup.exists()
    with seeded.store.session_factory.begin() as session:
        for row in session.query(RunModel):
            row.status = "completed"
    source = tmp_path / "original.h5ad"
    source.write_bytes(b"preserve me")
    counts = clear_records(seeded.store, backup)
    assert counts["runs"] == 5
    assert len(json.loads(backup.read_text(encoding="utf-8"))["tables"]["runs"]) == 5
    assert source.read_bytes() == b"preserve me"
    with seeded.store.engine.connect() as connection:
        assert connection.execute(text("SELECT value FROM preserved_records")).scalar() == "original"
    assert TestClient(app).get("/api/v1/experiments").json()["total"] == 0


def test_status_probes_resources_and_does_not_expose_secrets(app, monkeypatch):
    monkeypatch.setattr(
        "backend.app.services.system_status.gpu_status",
        lambda: {
            "detected": False,
            "devices": [],
            "message": "unavailable",
        },
    )
    response = TestClient(app).get("/api/v1/system-status")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["database"]["connected"] is True
    assert result["database"]["engine"] == "sqlite" and result["database"]["version"]
    assert result["system"]["cpu_logical_cores"] > 0
    assert set(result["workers"]) == {
        "online_enabled",
        "online_running",
        "online_pending",
        "sources",
    }
    assert result["workers"]["sources"]["worker_enabled"] in {"environment", "env_file", "default"}
    for forbidden in ("records.db", "database_url", "password", "username"):
        assert forbidden not in response.text
    monkeypatch.setattr(app.state.container.store.engine, "connect", lambda: (_ for _ in ()).throw(OSError()))
    assert TestClient(app).get("/api/v1/system-status").json()["database"]["connected"] is False


def test_gpu_probe_parses_numeric_and_unavailable_metrics(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: SimpleNamespace(
            stdout="0, NVIDIA A6000, 560.1, 49140, 256, 12, 45\n1, GPU B, 560.1, 8192, 0, [N/A], [N/A]"
        ),
    )
    result = gpu_status()
    assert len(result["devices"]) == 2
    assert result["devices"][0]["memory_total_bytes"] == 49140 * 1024**2
    assert result["devices"][1]["utilization_percent"] is None
    monkeypatch.setattr("subprocess.run", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    assert gpu_status()["detected"] is False


@pytest.mark.parametrize(
    "build,product_type,expected",
    [(19045, 1, "10"), (22000, 1, "11"), (26200, 1, "11"), (26100, 3, "Server"), (26100, 2, "Server")],
)
def test_windows_version_uses_build_and_distinguishes_server(monkeypatch, build, product_type, expected):
    import sys

    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("platform.release", lambda: "Server" if product_type != 1 else "10")
    monkeypatch.setattr("platform.version", lambda: f"10.0.{build}")
    monkeypatch.setattr(
        sys,
        "getwindowsversion",
        lambda: SimpleNamespace(major=10, minor=0, build=build, product_type=product_type),
        raising=False,
    )

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    registry = SimpleNamespace(
        HKEY_LOCAL_MACHINE=0,
        OpenKey=lambda *a: Key(),
        QueryValueEx=lambda key, name: ({"DisplayVersion": "25H2", "UBR": 9457}[name], 0),
    )
    monkeypatch.setitem(sys.modules, "winreg", registry)
    result = os_status()
    assert result["os_release"] == expected
    assert result["os_version"] == f"10.0.{build}.9457"
    assert result["os_display_version"] == "25H2"


def test_non_windows_status_retains_native_identity(monkeypatch):
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.release", lambda: "6.8.0")
    assert os_status()["os_release"] == "6.8.0"


def test_status_uses_effective_settings_and_live_environment(app, monkeypatch):
    settings = app.state.container.settings
    settings.gpu_available = False
    settings.worker_enabled = False
    monkeypatch.setattr("backend.app.services.system_status.cpu_model", lambda: "Host CPU A")
    monkeypatch.setattr("os.cpu_count", lambda: 24)
    monkeypatch.setattr("platform.python_version", lambda: "3.12.9")
    monkeypatch.setattr("importlib.metadata.version", lambda name: f"installed-{name}")
    monkeypatch.setattr(
        "backend.app.services.system_status.gpu_status",
        lambda: {"detected": True, "devices": [{"name": "Detected GPU A"}], "message": None},
    )
    client = TestClient(app)
    result = client.get("/api/v1/system-status").json()
    assert "limits" not in result
    assert result["system"]["cpu_model"] == "Host CPU A"
    assert result["system"]["cpu_logical_cores"] == 24
    assert result["system"]["python"] == "3.12.9"
    assert result["versions"]["torch"] == "installed-torch"
    assert result["gpu"]["detected"] is True and result["gpu"]["configured"] is False
    assert result["workers"]["online_enabled"] is False
    assert set(result["workers"]) == {
        "online_enabled",
        "online_running",
        "online_pending",
        "sources",
    }
    # A second manual check reads the changed values instead of a saved snapshot.
    monkeypatch.setattr("backend.app.services.system_status.cpu_model", lambda: "Host CPU B")
    result = client.get("/api/v1/system-status").json()
    assert result["system"]["cpu_model"] == "Host CPU B"


def test_setting_sources_expose_environment_override(monkeypatch):
    # A stray CELLLENS_WORKER_ENABLED=false in the launching shell silently beats .env;
    # the status response must name that source instead of only reporting "未启用".
    from backend.app.services.system_status import setting_sources

    monkeypatch.setenv("CELLLENS_WORKER_ENABLED", "false")
    monkeypatch.delenv("CELLLENS_GPU_AVAILABLE", raising=False)
    sources = setting_sources(("worker_enabled", "gpu_available"))
    assert sources["worker_enabled"] == "environment"
    assert sources["gpu_available"] in {"env_file", "default"}

    monkeypatch.delenv("CELLLENS_WORKER_ENABLED")
    assert setting_sources(("worker_enabled",))["worker_enabled"] in {"env_file", "default"}


def test_windows_cpu_model_uses_host_registry(monkeypatch):
    import sys

    from backend.app.services.system_status import cpu_model

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setitem(
        sys.modules,
        "winreg",
        SimpleNamespace(
            HKEY_LOCAL_MACHINE=0,
            OpenKey=lambda *a: Key(),
            QueryValueEx=lambda *a: ("  Actual processor name  ", 1),
        ),
    )
    assert cpu_model() == "Actual processor name"
