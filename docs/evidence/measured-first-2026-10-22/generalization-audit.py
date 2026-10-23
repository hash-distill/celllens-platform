"""Read-only model/protocol audit. Writes only generalization-* evidence here."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import pickle
import tomllib
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import torch
import yaml

ROOT = next(path for path in Path(__file__).resolve().parents if (path / "pyproject.toml").is_file())
OUT = Path(__file__).resolve().parent
MODEL_REV = "bb6a9562cbbf1fd152df14cc53b4cc7517c77175"
DATA_REV = "d790193bb2c93726541a75ca3fa873a92ed44da5"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def simple(value):
    if isinstance(value, torch.Tensor):
        return {"tensor_shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, dict):
        return {str(k): simple(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [simple(v) for v in value]
    if value is None or isinstance(value, (int, float, bool, str)):
        return value
    return {"type": type(value).__name__, "repr": repr(value)[:2000]}


def download(url: str, filename: str) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "CellLens-scientific-audit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        b = response.read()
        record = {"url": url, "retrieved_url": response.geturl(), "sha256": hashlib.sha256(b).hexdigest(), "size_bytes": len(b)}
    (OUT / filename).write_bytes(b)
    return b, record


def main():
    OUT.mkdir(exist_ok=True, parents=True)
    registry = json.loads((ROOT / "data/registry/models.json").read_text(encoding="utf-8"))
    packs = json.loads((ROOT / "backend/app/resources/inference_assets.json").read_text(encoding="utf-8"))["packs"]
    expected = {x["target"]: x for pack in packs for x in pack["files"]}
    report = {"created_at_utc": datetime.now(timezone.utc).isoformat(), "model_revision": MODEL_REV, "data_revision": DATA_REV, "arc_state_installed_version": importlib.metadata.version("arc-state"), "models": [], "sources": [], "checkpoint_training_exclusion_verified": False, "independent_held_out_validation": False}
    all_vocab = []
    for model in registry["models"]:
        slug = model["cell_line"].lower()
        model_dir = ROOT / model["model_dir"]
        config = yaml.safe_load((model_dir / "config.yaml").read_text(encoding="utf-8"))
        mapping = torch.load(model_dir / "pert_onehot_map.pt", map_location="cpu", weights_only=False)
        with (model_dir / "cell_type_onehot_map.pkl").open("rb") as f:
            contexts = pickle.load(f)
        vocab = sorted(str(k) for k in mapping)
        all_vocab.append(set(vocab))
        control = config["data"]["kwargs"]["control_pert"]
        genes = (ROOT / model["gene_list_path"]).read_text(encoding="utf-8").splitlines()
        files = []
        for path in sorted(model_dir.rglob("*")):
            if not path.is_file() or path.name == "source_manifest.json":
                continue
            rel = path.relative_to(ROOT).as_posix()
            got = digest(path)
            exp = expected.get(rel, {})
            files.append({"path": rel, "size_bytes": path.stat().st_size, "sha256": got, "matches_pinned_inference_manifest": got == exp.get("sha256"), "expected_sha256": exp.get("sha256")})
        b, source = download(f"https://huggingface.co/datasets/arcinstitute/State-Replogle-Filtered/raw/{DATA_REV}/{slug}.toml", f"generalization-upstream-{slug}.toml")
        report["sources"].append(source)
        split = tomllib.loads(b.decode("utf-8"))
        split_groups = split["fewshot"][f"replogle.{slug}"]
        tests = split_groups.get("test", [])
        train_declared = split_groups.get("train", [])
        item = {"cell_line": model["cell_line"], "model_id": model["id"], "config": config, "cell_type_mapping": simple(contexts), "vocabulary_count_including_control": len(vocab), "control_label_in_vocabulary": control in vocab, "non_control_vocabulary_count": len(vocab) - int(control in vocab), "registry_vocabulary_count": len(model["supported_perturbations"]), "registry_matches_mapping_casefold": {str(x).upper() for x in model["supported_perturbations"]} == {str(x).upper() for x in vocab}, "vocabulary": vocab, "feature_widths": sorted({len(v) for v in mapping.values()}), "gene_panel_count": len(genes), "gene_panel_sha256": digest(ROOT / model["gene_list_path"]), "files": files, "upstream_split": {"source": source, "dataset_paths": split.get("datasets"), "training": split.get("training"), "zeroshot": split.get("zeroshot"), "fewshot_keys": list(split["fewshot"]), "target_group_keys": list(split_groups), "test_count_including_control": len(tests), "test_non_control_count": len(set(tests) - {control}), "control_in_test": control in tests, "explicit_train_count": len(train_declared), "test_vocab_missing_exact": sorted(set(tests) - set(vocab)), "test_vocab_missing_casefold": sorted({x.upper() for x in tests} - {x.upper() for x in vocab}), "test_groups": tests, "val_groups": split_groups.get("val", [])}}
        if slug != "k562":
            local = ROOT / f"configs/splits/replogle-{slug}-fewshot-v1.json"
            local_split = json.loads(local.read_text())
            item["local_split_matches_fixed_source"] = local_split["source_split_sha256"] == source["sha256"] and set(local_split["test_groups"]) == set(tests)
        else:
            local = ROOT / "configs/splits/replogle-v1.json"
            local_split = json.loads(local.read_text())
            item["local_legacy_split"] = {"listed_test_count": len(local_split["test_groups"]), "declared_count": local_split["frozen_test_group_count"], "source_toml_matches_fixed_source": digest(ROOT / "configs/splits/replogle-k562-source.toml") == source["sha256"]}
        report["models"].append(item)
    report["all_four_vocabularies_identical"] = all(v == all_vocab[0] for v in all_vocab)
    # One trusted pinned checkpoint only. mmap reads metadata without GPU inference or allocating every tensor.
    checkpoint = ROOT / registry["models"][0]["checkpoint_path"]
    ckpt = torch.load(checkpoint, map_location="cpu", weights_only=False, mmap=True)
    report["checkpoint_metadata_sample"] = {"path": checkpoint.relative_to(ROOT).as_posix(), "sha256": registry["models"][0]["checkpoint_sha256"], "top_level_keys": list(ckpt), "non_tensor_top_level": {str(k): simple(v) for k, v in ckpt.items() if k not in {"state_dict", "optimizer_states", "lr_schedulers"}}, "state_dict_tensor_count": len(ckpt.get("state_dict", {})), "inspection_scope": "one K562 official checkpoint; CPU mmap metadata, no inference; no claim about unchecked metadata of other three checkpoints"}
    (OUT / "generalization-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"models": [{k: v for k, v in m.items() if k in {"cell_line", "vocabulary_count_including_control", "non_control_vocabulary_count", "control_label_in_vocabulary", "gene_panel_count", "local_split_matches_fixed_source", "local_legacy_split"}} | {"split_count": m["upstream_split"]["test_count_including_control"], "split_non_control_count": m["upstream_split"]["test_non_control_count"], "all_files_match": all(x["matches_pinned_inference_manifest"] for x in m["files"])} for m in report["models"]], "checkpoint_top_keys": list(ckpt), "hyper_parameters": simple(ckpt.get("hyper_parameters")), "output": str(OUT / "generalization-audit.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
