from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app


def test_health_reports_service_name(tmp_path):
    registry = tmp_path / "data" / "registry"
    registry.mkdir(parents=True)
    (registry / "models.json").write_text('{"models": []}', encoding="utf-8")
    (registry / "datasets.json").write_text('{"datasets": []}', encoding="utf-8")
    app = create_app(
        Settings(
            project_root=tmp_path,
            database_url=f"sqlite+pysqlite:///{(tmp_path / 'health.db').as_posix()}",
            create_database_schema=True,
        )
    )
    response = TestClient(app).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"service": "celllens", "status": "ok", "database": "ok"}
