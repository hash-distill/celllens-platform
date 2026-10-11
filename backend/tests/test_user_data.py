import json

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from scipy import sparse

from backend.app.config import Settings
from backend.app.main import create_app


@pytest.fixture
def application(tmp_path):
    root = tmp_path / "data" / "registry"
    root.mkdir(parents=True)
    (root / "models.json").write_text('{"models": []}')
    (root / "datasets.json").write_text('{"datasets": []}')
    app = create_app(
        Settings(
            _env_file=None,
            project_root=tmp_path,
            database_url=f"sqlite+pysqlite:///{tmp_path / 'private.db'}",
            create_database_schema=True,
            worker_enabled=False,
            data_worker_enabled=False,
        )
    )
    return app


def request_headers(client):
    return {}


def h5ad_bytes(tmp_path, values=None, *, duplicate=False):
    matrix = np.array([[3, 1, 0], [2, 2, 0], [0, 2, 6], [0, 1, 7]], dtype=float)
    if values is not None:
        matrix = np.asarray(values, dtype=float)
    genes = ["MYC", "LDHA", "RPI1"] if not duplicate else ["MYC", "MYC", "RPI1"]
    data = ad.AnnData(
        sparse.csr_matrix(matrix),
        obs=pd.DataFrame(
            {"condition": ["control", "control", "treated", "treated"]}, index=["c1", "c2", "c3", "c4"]
        ),
        var=pd.DataFrame(index=genes),
    )
    path = tmp_path / "input.h5ad"
    data.write_h5ad(path)
    return path.read_bytes()


def upload(client, headers, payload, **changes):
    metadata = {
        "name": "My experiment",
        "expression_scale": "raw_counts",
        "matrix_scope": "full_library",
        "input_layer": "X",
        "cell_context": "PBMC",
    }
    metadata.update(changes)
    return client.post(
        "/api/v1/datasets",
        headers=headers,
        data={"metadata": json.dumps(metadata)},
        files={"file": ("../../experiment.h5ad", payload)},
    )


def test_upload_workspace_requires_no_account(application, tmp_path):
    with TestClient(application) as client:
        assert client.get("/api/v1/datasets").status_code == 200
        assert client.get("/api/v1/analyses").status_code == 200
        assert upload(client, {}, h5ad_bytes(tmp_path)).status_code == 201
        assert not client.cookies
        for endpoint in ["login", "logout", "users"]:
            assert client.post("/api/v1/auth/" + endpoint, json={}).status_code == 404
        assert client.get("/api/v1/auth/me").status_code == 404


def test_shared_workspace_is_visible_from_another_browser(application, tmp_path):
    with TestClient(application) as alice, TestClient(application) as bob:
        ah = {}
        response = upload(alice, ah, h5ad_bytes(tmp_path))
        assert response.status_code == 201, response.text
        dataset = response.json()
        dataset_id = dataset["id"]
        assert dataset["summary"]["n_cells"] == 4
        assert dataset["summary"]["group_columns"]["condition"] == ["control", "treated"]
        assert len(dataset["sha256"]) == 64
        assert "path" not in dataset
        for suffix in ["", "/file"]:
            assert bob.get(f"/api/v1/datasets/{dataset_id}{suffix}").status_code == 200
        assert bob.get("/api/v1/datasets").json()["total"] == 1
        assert bob.get(f"/api/v1/datasets/{dataset_id}").json()["archived"] is False
        assert alice.get(f"/api/v1/datasets/{dataset_id}/file").content == h5ad_bytes(tmp_path)
        assert (
            alice.post(
                "/api/v1/analyses", headers=ah, json={"dataset_id": dataset_id, "kind": "explore"}
            ).status_code
            == 503
        )


@pytest.mark.parametrize(
    "changes,values,duplicate",
    [
        ({"matrix_scope": "selected_panel"}, None, False),
        ({"expression_scale": "unknown"}, None, False),
        ({}, [[-1, 1, 0]] * 4, False),
        ({}, [[0.5, 1, 0]] * 4, False),
        ({}, [[float("nan"), 1, 0]] * 4, False),
        ({}, None, True),
        ({"input_layer": "counts"}, None, False),
    ],
)
def test_invalid_uploads_are_rejected_without_files(application, tmp_path, changes, values, duplicate):
    with TestClient(application) as client:
        headers = request_headers(client)
        response = upload(client, headers, h5ad_bytes(tmp_path, values, duplicate=duplicate), **changes)
        assert response.status_code == 422, response.text
        assert client.get("/api/v1/datasets").json()["items"] == []
        assert not list(application.state.container.settings.user_data_root.rglob("*.h5ad"))


def test_upload_resource_limits_and_corruption(application):
    with TestClient(application) as client:
        headers = request_headers(client)
        assert upload(client, headers, b"not a HDF5 file").status_code == 422
        application.state.container.settings.max_upload_bytes = 100
        assert upload(client, headers, b"x" * 101).status_code == 413


def test_archive_keeps_download_and_disallows_new_jobs(application, tmp_path):
    with TestClient(application) as client:
        headers = request_headers(client)
        dataset = upload(client, headers, h5ad_bytes(tmp_path)).json()
        dataset_id = dataset["id"]
        assert client.post(f"/api/v1/datasets/{dataset_id}/archive", headers=headers).status_code == 200
        assert client.get(f"/api/v1/datasets/{dataset_id}").json()["archived"]
        assert client.get(f"/api/v1/datasets/{dataset_id}/file").status_code == 200
        assert (
            client.post(
                "/api/v1/analyses", headers=headers, json={"dataset_id": dataset_id, "kind": "explore"}
            ).status_code
            == 409
        )


def test_exploration_uses_full_library_and_descriptive_group_difference(tmp_path):
    from backend.app.user_data.analysis import explore_expression
    from backend.app.user_data.datasets import read_expression
    from backend.app.user_data.schemas import UploadMetadata

    h5ad_bytes(tmp_path)
    data, _ = read_expression(
        tmp_path / "input.h5ad",
        UploadMetadata(name="experiment", expression_scale="raw_counts", matrix_scope="full_library"),
    )
    linear = np.expm1(data.X.toarray())
    assert np.allclose(linear.sum(axis=1), 10000)
    report, table, _ = explore_expression(data, group_key="condition", reference_group="control", seed=42)
    assert report["comparison"]["method"] == "difference_of_group_means"
    myc = table[(table.gene == "MYC") & (table.group == "treated")].iloc[0]
    assert myc.mean_log1p_cp10k == 0
    assert myc.delta_log1p_cp10k < 0
    assert len(report["projection"]["points"]) == 4
    assert report["projection"]["method"] == "PCA"
    assert report["projection"]["input_scale"] == "log1p_cp10k"
    assert report["qc"]["n_cells"] == 4


def test_worker_result_download_shared_hash_and_recovery(application, tmp_path):
    from backend.app.user_data.models import UserAnalysisModel

    with TestClient(application) as alice, TestClient(application) as bob:
        ah = {}
        source = upload(alice, ah, h5ad_bytes(tmp_path)).json()
        container = application.state.container
        container.settings.data_worker_enabled = True
        response = alice.post(
            "/api/v1/analyses",
            headers=ah,
            json={
                "dataset_id": source["id"],
                "kind": "explore",
                "group_key": "condition",
                "reference_group": "control",
            },
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        # Simulate a process exit after claim. A new lock holder must recover it.
        with container.user_store.sessions.begin() as session:
            session.get(UserAnalysisModel, job_id).status = "running"
        container.data_worker.tick()
        job = alice.get(f"/api/v1/analyses/{job_id}").json()
        assert job["status"] == "completed", job
        report = alice.get(f"/api/v1/analyses/{job_id}/report").json()
        assert report["provenance"]["source_sha256"] == source["sha256"]
        assert report["provenance"]["analysis_version"] == "user-expression-v1"
        for suffix in ["", "/report", "/files/gene_summary.csv"]:
            assert bob.get(f"/api/v1/analyses/{job_id}{suffix}").status_code == 200
        downloaded = alice.get(f"/api/v1/analyses/{job_id}/files/gene_summary.csv")
        assert downloaded.status_code == 200
        assert downloaded.headers["cache-control"] == "no-store"
        assert "treated" in downloaded.text
        (container.settings.user_analysis_root / job_id / "gene_summary.csv").write_text("changed")
        assert alice.get(f"/api/v1/analyses/{job_id}/files/gene_summary.csv").status_code == 409


def test_worker_rejects_changed_source_and_invalid_group(application, tmp_path):
    with TestClient(application) as client:
        headers = request_headers(client)
        source = upload(client, headers, h5ad_bytes(tmp_path)).json()
        container = application.state.container
        container.settings.data_worker_enabled = True
        body = {"dataset_id": source["id"], "kind": "explore", "group_key": "missing"}
        assert client.post("/api/v1/analyses", headers=headers, json=body).status_code == 422
        body["group_key"] = "condition"
        body["reference_group"] = "unknown"
        assert client.post("/api/v1/analyses", headers=headers, json=body).status_code == 422
        body["reference_group"] = "control"
        job = client.post("/api/v1/analyses", headers=headers, json=body).json()
        (container.settings.user_data_root / (source["id"] + ".h5ad")).write_bytes(b"changed")
        container.data_worker.tick()
        failed = client.get(f"/api/v1/analyses/{job['id']}").json()
        assert failed["status"] == "failed"
        assert "SHA-256" in failed["error_message"]
        assert not failed["artifacts"]
        assert client.get(f"/api/v1/analyses/{job['id']}/report").status_code == 409


def test_hdf5_external_links_rejected(application, tmp_path):
    import h5py

    h5ad_bytes(tmp_path)
    path = tmp_path / "input.h5ad"
    with h5py.File(path, "a") as handle:
        handle["external"] = h5py.ExternalLink("other.h5ad", "X")
    with TestClient(application) as client:
        response = upload(client, request_headers(client), path.read_bytes())
        assert response.status_code == 422
        assert "链接" in response.json()["detail"]["message"]


def test_declared_layer_and_subset_library_denominator(tmp_path):
    from backend.app.user_data.datasets import read_expression
    from backend.app.user_data.schemas import UploadMetadata

    h5ad_bytes(tmp_path)
    path = tmp_path / "input.h5ad"
    data = ad.read_h5ad(path)
    data.layers["counts"] = data.X.copy()
    data.X = np.zeros(data.shape)
    data.obs["library_counts"] = [100, 100, 100, 100]
    data.write_h5ad(path)
    prepared, summary = read_expression(
        path,
        UploadMetadata(
            name="panel",
            expression_scale="raw_counts",
            matrix_scope="selected_panel",
            total_counts_key="library_counts",
            input_layer="counts",
        ),
    )
    assert np.allclose(np.expm1(prepared.X.toarray()).sum(axis=1), [400, 400, 800, 800])
    assert summary["normalization"]["total_counts_key"] == "library_counts"


def test_constant_expression_pca_returns_finite_coordinates(tmp_path):
    from backend.app.user_data.analysis import explore_expression
    from backend.app.user_data.datasets import read_expression
    from backend.app.user_data.schemas import UploadMetadata

    h5ad_bytes(tmp_path, [[5, 2, 1]] * 4)
    data, _ = read_expression(
        tmp_path / "input.h5ad",
        UploadMetadata(name="constant", expression_scale="raw_counts", matrix_scope="full_library"),
    )
    report, _, _ = explore_expression(data, group_key=None, reference_group=None, seed=42)
    json.dumps(report, allow_nan=False)
    assert report["projection"]["explained_variance_ratio"] == [0, 0]


def test_metabolism_uses_complete_uploaded_panel_and_frozen_database(application, tmp_path):
    import shutil

    from backend.app.config import PROJECT_ROOT
    from backend.app.services.scientific_analysis import _load_frozen_database

    frozen = PROJECT_ROOT / "data" / "registry" / "sccellfie" / "human"
    database, _ = _load_frozen_database(frozen)
    genes = list(database["rxn_by_gene"].columns)
    counts = np.random.default_rng(42).integers(1, 20, size=(4, len(genes)))
    data = ad.AnnData(
        sparse.csr_matrix(counts),
        obs=pd.DataFrame({"condition": ["a", "a", "b", "b"]}, index=["c1", "c2", "c3", "c4"]),
        var=pd.DataFrame(index=genes),
    )
    path = tmp_path / "complete.h5ad"
    data.write_h5ad(path)
    settings = application.state.container.settings
    shutil.copytree(frozen, settings.sccellfie_database_root)
    with TestClient(application) as client:
        headers = request_headers(client)
        dataset = upload(client, headers, path.read_bytes()).json()
        settings.data_worker_enabled = True
        response = client.post(
            "/api/v1/analyses",
            headers=headers,
            json={
                "dataset_id": dataset["id"],
                "kind": "metabolism",
                "group_key": "condition",
                "reference_group": "a",
            },
        )
        assert response.status_code == 202, response.text
        job_id = response.json()["id"]
        application.state.container.data_worker.tick()
        job = client.get(f"/api/v1/analyses/{job_id}").json()
        assert job["status"] == "completed", job
        report = client.get(f"/api/v1/analyses/{job_id}/report").json()
        assert report["metabolism"]["n_tasks"] == 218
        assert report["metabolism"]["n_reactions"] == 787
        official = client.get(f"/api/v1/analyses/{job_id}/files/official_completeness.json").json()
        assert official["panel_gene_count"] == 931
        assert official["overall_summary"]["n_tasks_fully_covered_all"] == 218
        assert official["overall_summary"]["n_genes_in_db_present_in_adata"] == 931
        assert report["metabolism"]["unscored_tasks"] == []


def test_cross_origin_mutation_and_oversize_body_are_rejected(application):
    with TestClient(application) as client:
        assert upload(client, {"Origin": "https://elsewhere.example"}, b"file").status_code == 403
        assert (
            client.post("/api/v1/analyses", headers={"Sec-Fetch-Site": "cross-site"}, json={}).status_code
            == 403
        )
        application.state.container.settings.max_upload_bytes = 100
        assert upload(client, {}, b"x" * 70000).status_code == 413


def test_sparse_and_dense_expression_statistics_agree(tmp_path):
    from backend.app.user_data.analysis import explore_expression
    from backend.app.user_data.datasets import read_expression
    from backend.app.user_data.schemas import UploadMetadata

    h5ad_bytes(tmp_path)
    data, _ = read_expression(
        tmp_path / "input.h5ad",
        UploadMetadata(name="values", expression_scale="raw_counts", matrix_scope="full_library"),
    )
    sparse_report, sparse_table, _ = explore_expression(
        data, group_key="condition", reference_group="control", seed=42
    )
    data.X = data.X.toarray()
    dense_report, dense_table, _ = explore_expression(
        data, group_key="condition", reference_group="control", seed=42
    )
    pd.testing.assert_frame_equal(sparse_table, dense_table)
    assert dense_report["qc"] == sparse_report["qc"]


def test_upload_rejects_malformed_sparse_indices(application, tmp_path):
    import h5py

    h5ad_bytes(tmp_path)
    path = tmp_path / "input.h5ad"
    with h5py.File(path, "a") as handle:
        handle["X/indices"][0] = -1
    with TestClient(application) as client:
        assert upload(client, request_headers(client), path.read_bytes()).status_code == 422


def test_upload_rejects_complex_expression(application, tmp_path):
    data = ad.AnnData(
        np.array([[1 + 2j, 1 + 2j], [2 + 1j, 2 + 1j]]),
        obs=pd.DataFrame(index=["one", "two"]),
        var=pd.DataFrame(index=["LDHA", "MYC"]),
    )
    path = tmp_path / "complex.h5ad"
    data.write_h5ad(path)
    with TestClient(application) as client:
        response = upload(client, request_headers(client), path.read_bytes(), expression_scale="cp10k")
        assert response.status_code == 422


def test_capabilities_require_complete_pinned_metabolic_database(application):
    root = application.state.container.settings.sccellfie_database_root
    root.mkdir(parents=True)
    (root / "manifest.json").write_text('{"enabled": true, "files": {}}')
    with TestClient(application) as client:
        capabilities = client.get("/api/v1/data-capabilities").json()
        assert not capabilities["metabolism_ready"]
        assert capabilities["state_user_prediction_enabled"] is False


def test_workspace_search_filters_named_jobs_and_global_queue_limit(application, tmp_path):
    with TestClient(application) as client:
        dataset = upload(client, {}, h5ad_bytes(tmp_path), name="PBMC experiment").json()
        assert client.get("/api/v1/datasets", params={"q": "PBMC"}).json()["total"] == 1
        assert client.get("/api/v1/datasets", params={"q": "unknown"}).json()["total"] == 0
        application.state.container.settings.data_worker_enabled = True
        body = {"dataset_id": dataset["id"], "kind": "explore", "name": "First analysis"}
        for _ in range(3):
            response = client.post("/api/v1/analyses", json=body)
            assert response.status_code == 202
            assert response.json()["name"] == "First analysis"
        assert client.post("/api/v1/analyses", json=body).status_code == 429
        assert (
            client.get("/api/v1/analyses", params={"dataset_id": dataset["id"], "status": "queued"}).json()[
                "total"
            ]
            == 3
        )
        assert client.get("/api/v1/analyses", params={"status": "completed"}).json()["total"] == 0


def test_legacy_owned_records_are_preserved_but_not_published(application, tmp_path):
    from backend.app.user_data.models import DatasetModel, UserAnalysisModel, UserModel
    from backend.app.user_data.store import now

    store = application.state.container.user_store
    with TestClient(application) as client:
        dataset = upload(client, {}, h5ad_bytes(tmp_path)).json()
        application.state.container.settings.data_worker_enabled = True
        job = client.post("/api/v1/analyses", json={"dataset_id": dataset["id"]}).json()
        with store.sessions.begin() as session:
            session.add(
                UserModel(
                    id="legacy",
                    username="legacy",
                    password_hash="disabled",
                    role="user",
                    active=False,
                    failed_logins=0,
                    created_at=now(),
                )
            )
            session.flush()
            session.get(DatasetModel, dataset["id"]).owner_id = "legacy"
            session.get(UserAnalysisModel, job["id"]).owner_id = "legacy"
        assert client.get("/api/v1/datasets").json()["total"] == 0
        assert client.get("/api/v1/analyses").json()["total"] == 0
        for suffix in ["", "/file"]:
            assert client.get("/api/v1/datasets/" + dataset["id"] + suffix).status_code == 404
        for suffix in ["", "/report", "/files/report.json"]:
            assert client.get("/api/v1/analyses/" + job["id"] + suffix).status_code == 404
        with store.sessions() as session:
            assert session.get(DatasetModel, dataset["id"]) is not None
            assert session.get(UserAnalysisModel, job["id"]) is not None
