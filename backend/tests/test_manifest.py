from backend.app.core.run_manifest import manifest_hash


def test_manifest_hash_is_order_independent():
    left = {"cell_line": "K562", "seed": 42, "perturbation": "AARS"}
    right = {"perturbation": "AARS", "cell_line": "K562", "seed": 42}
    assert manifest_hash(left) == manifest_hash(right)
