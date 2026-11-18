import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.tests.test_api_runs import _settings, _write_registry


@pytest.fixture
def local_client(tmp_path):
    _write_registry(tmp_path)
    with TestClient(create_app(_settings(tmp_path)), client=("127.0.0.1", 45000)) as client:
        yield client


@pytest.mark.parametrize("host", ["localhost:8028", "127.0.0.1:8028", "[::1]:8028"])
def test_loopback_authorities_remain_usable(local_client, host):
    assert local_client.get("/api/v1/runs", headers={"host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    ["rebind.example:8028", "localhost.evil.example", "testserver", "user@localhost", "localhost:99999"],
)
def test_rebinding_authority_cannot_read_workspace(local_client, host):
    response = local_client.get("/api/v1/runs", headers={"host": host})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "LOCAL_HOST_REJECTED"
    assert "items" not in response.json()


def test_matching_attacker_origin_does_not_bypass_host_check(local_client):
    response = local_client.post(
        "/api/v1/runs",
        headers={"host": "rebind.example:8028", "origin": "http://rebind.example:8028"},
        json={"cell_line": "K562", "perturbation": "MYC"},
    )
    assert response.status_code == 400
    assert local_client.get("/api/v1/runs", headers={"host": "localhost"}).json()["total"] == 0


def test_duplicate_hosts_are_rejected(local_client):
    response = local_client.get("/api/v1/runs", headers=[("host", "localhost"), ("host", "rebind.example")])
    assert response.status_code == 400
