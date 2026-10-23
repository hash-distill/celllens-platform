"""Malformed H5AD observation metadata must degrade to unknown instead of a server error."""

from types import SimpleNamespace

import pytest

from backend.app.services.control_metadata import control_cell_count


@pytest.mark.parametrize("malformed", ["categories_group", "index_matrix", "codes_matrix"])
def test_invalid_observation_structure_returns_unknown(tmp_path, malformed):
    h5py = pytest.importorskip("h5py")
    path = tmp_path / "control.h5ad"
    with h5py.File(path, "w") as handle:
        obs = handle.create_group("obs")
        obs.attrs["_index"] = "index"
        obs.create_dataset("index", data=[[b"a"], [b"b"]] if malformed == "index_matrix" else [b"a", b"b"])
        obs.create_dataset("cell_line", data=[b"K562", b"K562"])
        gene = obs.create_group("gene")
        if malformed == "categories_group":
            gene.create_group("categories")
        else:
            gene.create_dataset("categories", data=[b"non-targeting"])
        gene.create_dataset("codes", data=[[0], [0]] if malformed == "codes_matrix" else [0, 0])
    dataset = SimpleNamespace(enabled=True, path=lambda _: path)
    registry = SimpleNamespace(dataset_for=lambda *a, **kw: dataset, asset_is_valid_cached=lambda *a: True)
    assert control_cell_count(registry, "K562") is None
