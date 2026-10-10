"""Fetch SHA-verified official SE/ST-SE assets without changing active registries."""

import concurrent.futures
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SE_REVISION = "5a9a80f44f7ce32ce57059933ef0d735d7c10ce5"
ST_REVISION = "d1441f5587ace12c46247b3703c7d25f24f8abb6"


def get(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def download(repo, revision, entry, target):
    expected = entry.get("lfs", {}).get("oid")
    if target.exists():
        actual = digest(target)
        if expected and actual != expected:
            raise ValueError(f"Existing asset hash mismatch: {target.name}")
        return actual
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://huggingface.co/{repo}/resolve/{revision}/{entry['path']}"
    partial = target.with_suffix(target.suffix + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
    with urllib.request.urlopen(request, timeout=120) as response:
        if offset and response.status != 206:
            raise ValueError("Server did not honour resumed range")
        with partial.open("ab" if offset else "wb") as handle:
            while chunk := response.read(4 << 20):
                handle.write(chunk)
    if partial.stat().st_size != entry["size"]:
        raise ValueError(f"Downloaded size mismatch: {entry['path']}")
    actual = digest(partial)
    if expected and actual != expected:
        raise ValueError(f"Downloaded SHA mismatch: {entry['path']}")
    partial.replace(target)
    print(f"verified {repo} {entry['path']} {actual}", flush=True)
    return actual


def prepare(repo, revision, subdirectory, filenames, destination):
    path = f"/{subdirectory}" if subdirectory else ""
    entries = json.loads(
        get(f"https://huggingface.co/api/models/{repo}/tree/{revision}{path}?recursive=true")
    )
    by_path = {entry["path"]: entry for entry in entries}
    files = {}
    for filename in filenames:
        full = f"{subdirectory}/{filename}" if subdirectory else filename
        entry = by_path[full]
        files[filename] = download(repo, revision, entry, destination / filename)
    manifest = {
        "repo": repo,
        "revision": revision,
        "subdirectory": subdirectory,
        "files": files,
        "activation": "experimental only; active registry unchanged",
    }
    (destination / "source_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main():
    st_files = [
        "config.yaml",
        "var_dims.pkl",
        "pert_onehot_map.pt",
        "batch_onehot_map.pkl",
        "cell_type_onehot_map.pkl",
        "checkpoints/best.ckpt",
    ]
    jobs = [
        (
            "arcinstitute/SE-600M",
            SE_REVISION,
            "",
            [
                "config.yaml",
                "model.safetensors",
                "protein_embeddings.pt",
                "README.md",
                "MODEL_LICENSE.md",
                "MODEL_ACCEPTABLE_USE_POLICY.md",
                "LICENSE.md",
            ],
            ROOT / "models/se600m-epoch16",
        )
    ]
    jobs.extend(
        (
            "arcinstitute/st-se-replogle-full",
            ST_REVISION,
            f"{context}_0.99",
            st_files,
            ROOT / f"models/st-se-full-{context}",
        )
        for context in ("k562", "rpe1", "jurkat", "hepg2")
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(prepare, *job) for job in jobs]
        for future in futures:
            future.result()


if __name__ == "__main__":
    main()
