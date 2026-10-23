"""Companion hashes for the pinned official STATE bundles shipped by this application."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def official_bundles() -> list[dict]:
    path = Path(__file__).resolve().parents[1] / "resources/inference_assets.json"
    return json.loads(path.read_text(encoding="utf-8"))["packs"]


def companion_files(payload: dict) -> list[dict]:
    # Generic/custom registry models keep their own contract. Known official weights
    # must also carry their pinned maps, variable dimensions and upstream config.
    for bundle in official_bundles():
        checkpoint = next(item for item in bundle["files"] if item["name"] == "checkpoints/final.ckpt")
        if bundle["cell_line"] == payload["cell_line"] and checkpoint["sha256"] == payload.get(
            "checkpoint_sha256"
        ):
            return [item for item in bundle["files"] if item != checkpoint]
    return []
