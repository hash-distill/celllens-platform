import csv
import re
import shutil
from pathlib import Path

import pytest

from backend.app.services.gene_education import (
    DISPLAY_TRANSLATIONS,
    TASK_GUIDES,
    categories_for,
    classify_gene,
    load_annotations,
)
from backend.app.services.gene_identity import GeneIdentityAdapter

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
    # Keep the curated explanations for the original seven fully covered steps.
    for key in (
        "Fructose degradation (to glucose-3-phosphate)",
        "Fucosylation (addition of fucose)",
        "Malate to pyruvate conversion",
        "Mevalonate synthesis",
        "Presence of the thioredoxin system through the thioredoxin reductase activity",
        "Reactive oxygen species detoxification (H2O2 to H2O)",
        "Tetrahydrofolate synthesis",
    ):
        row = TASK_GUIDES[key]
        for key in ("name_zh", "name_en", "description_zh", "description_en", "scope_zh", "scope_en"):
            assert row[key]
        assert row["source_url"].startswith("https://www.uniprot.org/uniprotkb/")
    assert "丙糖磷酸" in TASK_GUIDES["Fructose degradation (to glucose-3-phosphate)"]["name_zh"]
    assert "NADH" in TASK_GUIDES["Malate to pyruvate conversion"]["description_en"]
    assert "O2" in TASK_GUIDES["Reactive oxygen species detoxification (H2O2 to H2O)"]["description_en"]


def test_every_frozen_task_has_distinct_chinese_name_and_description():
    with (REGISTRY / "sccellfie/human/Task-Info.csv").open(encoding="utf-8-sig", newline="") as stream:
        task_ids = {row["Task"] for row in csv.DictReader(stream)}
    assert task_ids <= TASK_GUIDES.keys(), sorted(task_ids - TASK_GUIDES.keys())
    for identifier in task_ids:
        guide = TASK_GUIDES[identifier]
        for field in ("name", "description", "scope"):
            assert re.search(r"[\u4e00-\u9fff]", guide[field + "_zh"]), (identifier, field)
            assert guide[field + "_zh"] != guide[field + "_en"], (identifier, field)
        assert guide["source_url"].startswith("https://")


def test_chinese_gene_names_follow_hgnc_identity_and_preserve_originals():
    document = load_annotations(REGISTRY)
    for symbol, fragment in (("TPI1", "丙糖磷酸"), ("ALDOA", "醛缩酶"), ("MT-CO1", "细胞色素")):
        gene = classify_gene(symbol, document)
        assert fragment in (gene.get("name_zh") or ""), symbol
        assert gene["name_zh"] != gene["name_en"]
    legacy = classify_gene("COX1", document, "HGNC:7419")
    assert legacy["approved_symbol"] == "MT-CO1"
    assert legacy.get("name_zh") == classify_gene("MT-CO1", document).get("name_zh")
    assert not classify_gene("MYC_LIKE", document).get("name_zh")


def test_all_currently_covered_metabolic_genes_have_chinese_names():
    annotations = load_annotations(REGISTRY)
    identity = GeneIdentityAdapter.load(REGISTRY / "gene_identity", REGISTRY / "sccellfie/human")
    with (REGISTRY / "sccellfie/human/Rxn_by_Gene.csv").open(encoding="utf-8-sig", newline="") as stream:
        database_genes = set(next(csv.reader(stream))[1:])
    for panel_path in REGISTRY.glob("state_*_genes.txt"):
        panel = {identity.resolve(gene)["analysis_symbol"] for gene in panel_path.read_text().splitlines()}
        present = panel & database_genes
        assert present
        missing = []
        for symbol in present:
            identifier = identity.document["database_genes"][symbol]["hgnc_id"]
            gene = classify_gene(symbol, annotations, identifier)
            if not re.search(r"[\u4e00-\u9fff]", gene.get("name_zh") or ""):
                missing.append(symbol)
        assert not missing, (panel_path.name, missing)


def test_all_frozen_task_groups_are_translated():
    with (REGISTRY / "sccellfie/human/Task-Info.csv").open(encoding="utf-8-sig", newline="") as stream:
        groups = {row[field] for row in csv.DictReader(stream) for field in ("System", "Subsystem")}
    assert groups <= DISPLAY_TRANSLATIONS["groups"].keys()
    assert all(re.search(r"[\u4e00-\u9fff]", DISPLAY_TRANSLATIONS["groups"][key]) for key in groups)
