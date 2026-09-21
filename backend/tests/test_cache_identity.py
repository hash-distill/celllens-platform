from pathlib import Path

from backend.app.core.cache import build_cache_key, code_fingerprint
from backend.app.schemas import CreateRunRequest


def test_cache_key_changes_with_request_or_assets():
    request = CreateRunRequest(cell_line="K562", perturbation="MYC", n_cells=64)
    first = build_cache_key(request, {"checkpoint": "a"}, code_hash="code", database_hash="db")
    repeated = build_cache_key(request, {"checkpoint": "a"}, code_hash="code", database_hash="db")
    changed = build_cache_key(request, {"checkpoint": "b"}, code_hash="code", database_hash="db")

    assert first == repeated
    assert first != changed
    assert len(first) == 64


def test_code_fingerprint_is_order_independent_and_content_sensitive(tmp_path: Path):
    (tmp_path / "backend" / "app").mkdir(parents=True)
    source = tmp_path / "backend" / "app" / "example.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")

    first = code_fingerprint(tmp_path)
    source.write_text("VALUE = 2\n", encoding="utf-8")
    second = code_fingerprint(tmp_path)

    assert first != second
