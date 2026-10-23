"""CPU subprocess entry point. Publish a verified result atomically."""

import argparse
import copy
import json
import sys
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from backend.app.core.run_manifest import atomic_write_json, file_sha256
from backend.app.services.measured_analysis import VERSION, analyse_measured, render_report
from backend.app.services.measured_inputs import prepare_inputs
from backend.app.services.resource_control import watch_parent


def execute_measured_job(
    root, request, staging, final, report, *, inputs=None, metabolism=True, compute_umap=True
):
    staging.mkdir(parents=True, exist_ok=True)
    inputs = copy.deepcopy(inputs) if inputs is not None else prepare_inputs(root, request, staging, report)
    summary = analyse_measured(
        root, request, inputs, staging, report, metabolism=metabolism, compute_umap=compute_umap
    )
    # Paths survive the atomic directory move; external registered sources remain unchanged.
    for entry in summary["provenance"]["groups"].values():
        path = Path(entry["path"]).resolve()
        if path.is_relative_to(staging.resolve()):
            path = final / path.relative_to(staging.resolve())
        entry["path"] = path.relative_to(root.resolve()).as_posix()
    atomic_write_json(staging / "summary.json", summary)
    render_report(summary, staging)
    packages = {}
    for name in ("anndata", "numpy", "pandas", "scikit-learn", "umap-learn", "scCellFie"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "unavailable"
    files = {
        path.relative_to(staging).as_posix(): file_sha256(path)
        for path in staging.rglob("*")
        if path.is_file() and path.name not in {"request.json", "manifest.json"}
    }
    manifest = {
        "id": request["id"],
        "source_kind": "measured",
        "analysis_version": VERSION,
        "request": request,
        "inputs": summary["provenance"],
        "files": files,
        "packages": packages,
    }
    atomic_write_json(staging / "manifest.json", manifest)
    if final.exists():
        raise ValueError("目标实测分析已存在，未覆盖原结果")
    staging.replace(final)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--parent-pid", required=True, type=int)
    args = parser.parse_args()
    threading.Thread(target=watch_parent, args=(args.parent_pid,), daemon=True).start()
    root = Path(args.root).resolve()
    path = Path(args.request_file).resolve()
    base = root / "data/derived/measured"
    if not path.is_relative_to(base) or path.name != "request.json":
        raise ValueError("Invalid measured worker input path")
    request = json.loads(path.read_text(encoding="utf-8"))
    from backend.app.services.measured_results import result_directory

    final = result_directory(root, request["id"])

    def report(progress, message):
        print(json.dumps({"progress": progress, "message": message}, ensure_ascii=True), flush=True)

    try:
        execute_measured_job(root, request, path.parent, final, report)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=True), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
