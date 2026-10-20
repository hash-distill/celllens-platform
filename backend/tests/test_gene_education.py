import shutil
from pathlib import Path

import pytest

from backend.app.services.gene_education import (
    TASK_GUIDES,
    categories_for,
    classify_gene,
    load_annotations,
)

REGISTRY = Path(__file__).resolve().parents[2] / "data" / "registry"


def test_frozen_classes_map_hgnc_identity_without_name_guessing():
    document = load_annotations(REGISTRY)
    assert document is not None
    assert classify_gene("MYC", document)["category_ids"] == ["PC00264"]
    assert classify_gene("TPI1", document)["category_ids"] == ["PC00135"]
    assert classify_gene("ALDOA", document)["category_ids"] == ["PC00144"]
    assert classify_gene("ACTB", document)["category_ids"] == ["PC00085"]
    assert classify_gene("MYC_LIKE", document)["category_ids"] == ["unclassified"]
    by_id = classify_gene("old_database_label", document, "HGNC:12009")
    assert by_id["category_ids"] == ["PC00135"]
    assert by_id["approved_symbol"] == "TPI1"


def test_class_counts_preserve_multiple_roles_and_bilingual_definitions():
    document = load_annotations(REGISTRY)
    genes = [
        {"category_ids": ["PC00031", "PC00263"]},
        {"category_ids": ["PC00031"]},
        {"category_ids": ["unclassified"]},
    ]
    categories = categories_for(genes, document)
    assert {row["id"]: row["count"] for row in categories} == {
        "PC00031": 2,
        "PC00263": 1,
        "unclassified": 1,
    }
    for row in categories:
        assert row["name_zh"] and row["name_en"]
        assert row["description_zh"] and row["description_en"]


def test_classification_revalidates_cached_file_hash(tmp_path):
    folder = tmp_path / "gene_annotations"
    shutil.copytree(REGISTRY / "gene_annotations", folder)
    assert load_annotations(tmp_path) is not None
    path = folder / "human.json.gz"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ValueError, match="hash validation"):
        load_annotations(tmp_path)


def test_task_guides_keep_local_steps_and_bilingual_scope():
    assert len(TASK_GUIDES) == 7
    for row in TASK_GUIDES.values():
        for key in ("name_zh", "name_en", "description_zh", "description_en", "scope_zh", "scope_en"):
            assert row[key]
        assert row["source_url"].startswith("https://www.uniprot.org/uniprotkb/")
    assert "丙糖磷酸" in TASK_GUIDES["Fructose degradation (to glucose-3-phosphate)"]["name_zh"]
    assert "NADH" in TASK_GUIDES["Malate to pyruvate conversion"]["description_en"]
    assert "O2" in TASK_GUIDES["Reactive oxygen species detoxification (H2O2 to H2O)"]["description_en"]
