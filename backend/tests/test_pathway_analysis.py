from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import fisher_exact

from backend.app.services.pathway_analysis import (
    PathwayResourceError,
    analyze_pathways,
    benjamini_hochberg,
    load_reactome_resource,
)


def resource(tmp_path: Path, sets: dict[str, list[str]]) -> Path:
    gmt = "\n".join(f"Pathway {i}\tR-HSA-{i}\t" + "\t".join(genes) for i, genes in sets.items()).encode()
    archive = tmp_path / "sets.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("sets.gmt", gmt)
    manifest = {
        "species": "Homo sapiens",
        "identifier_type": "gene_symbol",
        "pathway_count": len(sets),
        "archive_file": archive.name,
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "gmt_member": "sets.gmt",
        "gmt_sha256": hashlib.sha256(gmt).hexdigest(),
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def expression(n: int = 100) -> pd.DataFrame:
    genes = [f"G{i:03d}" for i in range(n)]
    delta = np.arange(n, dtype=float) - n / 2
    return pd.DataFrame({"control": n, "observed": n + delta, "observed_delta": delta}, index=genes)


def test_contingencies_match_one_sided_fisher_and_global_bh(tmp_path):
    frame = expression()
    genes = list(frame.index)
    path = resource(tmp_path, {"1": genes, "2": genes[-10:], "3": genes[:20], "4": genes[30:40]})
    doc, table = analyze_pathways(frame, genes, manifest_path=path)
    assert doc["status"] == "complete"
    assert len(table) == 8
    assert doc["candidates"] == {"up": genes[-5:][::-1], "down": genes[:5]}
    assert set(table.direction) == {"up", "down"}
    for row in doc["results"]:
        n, k, s, h = row["background_size"], row["pathway_size"], row["candidate_size"], row["hit_count"]
        fisher = fisher_exact([[h, s - h], [k - h, n - k - s + h]], alternative="greater").pvalue
        assert row["p_value"] == pytest.approx(fisher, rel=1e-12, abs=1e-14)
    # Explicit independent BH construction over BOTH directions, including zero hits.
    ordered = sorted(enumerate(table.p_value), key=lambda pair: pair[1])
    expected = [1.0] * len(table)
    running = 1.0
    for rank in range(len(ordered), 0, -1):
        idx, p = ordered[rank - 1]
        running = min(running, p * len(ordered) / rank)
        expected[idx] = running
    assert table.fdr.to_list() == pytest.approx(expected)
    zero_hits = table.loc[table.hit_count == 0]
    assert (zero_hits.p_value == 1).all()
    assert (zero_hits.fdr == 1).all()
    assert "处理效应显著" in doc["interpretation"]
    json.dumps(doc, allow_nan=False)


def test_bh_zeros_ties_and_invalid_values():
    assert benjamini_hochberg([0, 0.01, 0.01, 0.5, 1]) == pytest.approx([0, 1 / 60, 1 / 60, 0.625, 1])
    assert benjamini_hochberg([]) == []
    for invalid in ([np.nan], [-0.1], [1.1], [np.inf]):
        with pytest.raises(ValueError):
            benjamini_hochberg(invalid)


def test_background_is_detectable_comparable_mapped_not_whole_resource(tmp_path):
    frame = expression(200)
    path = resource(tmp_path, {"1": list(frame.index) + ["UNMEASURED"], "2": list(frame.index[:6])})
    detectable = list(frame.index[:100]) + ["NOT_IN_TABLE"]
    frame.loc["G001", "control"] = np.nan
    frame.loc["G002", "observed_delta"] = np.inf
    frame.loc["G003", "observed_delta"] = 200
    frame = pd.concat([frame, frame.loc[["G004"]]])
    frame.loc["MISSING_SYMBOL"] = [0, 1, 1]
    detectable.append("MISSING_SYMBOL")
    doc, _ = analyze_pathways(frame, detectable, manifest_path=path)
    assert len(doc["background_genes"]) == 96
    assert not {"G001", "G002", "G003", "G004", "UNMEASURED"} & set(doc["background_genes"])
    assert doc["unmapped_genes"] == ["MISSING_SYMBOL"]
    assert doc["excluded_duplicate_symbols"] == ["G004"]
    assert doc["excluded_inconsistent_delta_symbols"] == ["G003"]
    assert doc["parameters"]["candidate_cap_per_direction"] == 4
    assert doc["candidates"]["up"] == []
    assert len(doc["candidates"]["down"]) == 4
    assert doc["coverage"]["eligible_pathway_count"] == 1  # 6-member pathway intersects U at 2 genes


def test_small_background_floor_and_no_candidate_direction(tmp_path):
    frame = expression(19)
    path = resource(tmp_path, {"1": list(frame.index)})
    doc, table = analyze_pathways(frame, frame.index, manifest_path=path)
    assert doc["status"] == "no_candidates"
    assert doc["parameters"]["candidate_rounding"] == "floor"
    assert doc["parameters"]["candidate_cap_per_direction"] == 0
    assert table.empty
    frame = expression(100)
    frame["observed"] = frame["control"]
    frame["observed_delta"] = 0
    path = resource(tmp_path, {"1": list(frame.index)})
    doc, table = analyze_pathways(frame, frame.index, manifest_path=path)
    assert doc["status"] == "no_candidates"
    assert table.empty
    frame.loc["G001", ["observed", "observed_delta"]] = [101, 1]
    doc, table = analyze_pathways(frame, frame.index, manifest_path=path)
    assert doc["candidates"] == {"up": ["G001"], "down": []}
    assert len(table) == 1


def test_order_and_tie_repeatability(tmp_path):
    frame = expression(100)
    frame["observed"] = 101
    frame["observed_delta"] = 1
    path = resource(tmp_path, {"1": list(frame.index), "2": list(frame.index[:5])})
    doc, table = analyze_pathways(frame, frame.index, manifest_path=path)
    other_doc, other_table = analyze_pathways(frame.iloc[::-1], reversed(frame.index), manifest_path=path)
    assert doc == other_doc
    pd.testing.assert_frame_equal(table, other_table)
    assert doc["candidates"]["up"] == list(frame.index[:5])


def test_low_coverage_unknown_and_no_eligible_pathways(tmp_path):
    frame = expression(200)
    path = resource(tmp_path, {"1": list(frame.index[:20])})
    doc, _ = analyze_pathways(frame, frame.index, manifest_path=path)
    assert doc["status"] == "low_coverage"
    assert doc["coverage"]["mapping_fraction"] == 0.1
    assert doc["warnings"] == ["low_mapping_coverage"]
    doc, table = analyze_pathways(frame, frame.index, manifest_path=path, species="Mus musculus")
    assert doc["status"] == "unsupported_species"
    assert table.empty
    doc, table = analyze_pathways(frame, ["unmapped"], manifest_path=path)
    assert doc["status"] == "no_mapped_background"
    assert table.empty
    assert doc["coverage"]["mapping_fraction"] is None
    doc, table = analyze_pathways(frame, frame.index, manifest_path=path, min_pathway_size=21)
    assert doc["status"] == "no_eligible_pathways"
    assert table.empty


def test_resource_changes_are_rejected_not_cached(tmp_path):
    path = resource(tmp_path, {"1": list(expression().index)})
    load_reactome_resource(path)
    with (tmp_path / "sets.zip").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(PathwayResourceError, match="SHA-256"):
        load_reactome_resource(path)
    with pytest.raises(PathwayResourceError):
        load_reactome_resource(tmp_path / "absent.json")


def test_gmt_digest_and_prepare_upstream_guard(tmp_path):
    from scripts.prepare_reactome import prepare

    path = resource(tmp_path, {"1": list(expression().index)})
    manifest = json.loads(path.read_text())
    manifest["gmt_sha256"] = "0" * 64
    path.write_text(json.dumps(manifest))
    with pytest.raises(PathwayResourceError, match="GMT SHA-256"):
        load_reactome_resource(path)
    with pytest.raises(ValueError, match="SHA-256"):
        prepare(tmp_path / "out", tmp_path / "sets.zip")
    assert not (tmp_path / "out").exists()


def test_bundled_official_resource_and_exact_symbol_mapping():
    manifest, pathways = load_reactome_resource()
    assert manifest["release"] == "98"
    assert manifest["license"] == "CC0-1.0"
    assert len(pathways) == 2874
    frame = pd.DataFrame(
        {"control": [1, 1, 1], "observed": [2, 2, 2], "observed_delta": [1, 1, 1]},
        index=["TP53", "tp53", "ENSG00000141510"],
    )
    doc, table = analyze_pathways(frame, frame.index)
    assert doc["background_genes"] == ["TP53"]
    assert doc["unmapped_genes"] == ["ENSG00000141510", "tp53"]
    assert table.empty


def test_size_boundaries_are_measured_after_intersection(tmp_path):
    import math

    frame = expression(600)
    genes = list(frame.index)
    path = resource(
        tmp_path,
        {
            "1": genes,
            "2": genes[:500],
            "3": genes[:501],
            "4": genes[:5],
            "5": genes[:4] + ["UNMEASURED"],
        },
    )
    doc, table = analyze_pathways(frame, genes, manifest_path=path)
    assert {row["pathway_id"] for row in doc["eligible_pathways"]} == {"R-HSA-2", "R-HSA-4"}
    assert len(table) == 4
    row = next(row for row in doc["results"] if row["pathway_id"] == "R-HSA-4" and row["direction"] == "down")
    # All five members are among 30 down candidates in a 600-gene U.
    exact = math.comb(595, 25) / math.comb(600, 30)
    assert row["hit_count"] == 5
    assert row["p_value"] == pytest.approx(exact, rel=1e-12)
