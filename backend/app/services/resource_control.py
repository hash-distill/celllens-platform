"""Extract a bounded real control population from a pinned official remote atlas."""

import argparse
import asyncio
import contextlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any


async def run_control_process(root: Path, cell: str, output: Path, report: Any) -> None:
    flags: dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "backend.app.services.resource_control",
        "--root",
        str(root),
        "--cell-line",
        cell,
        "--output",
        str(output),
        "--parent-pid",
        str(os.getpid()),
        cwd=root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        **flags,
    )
    try:
        async with asyncio.timeout(1800):
            assert process.stdout is not None
            async for line in process.stdout:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record.get("message"), str):
                    report(record["message"][:200])
            if await process.wait() != 0:
                raise ValueError(
                    "对照提取失败，请确认已安装 model/report 依赖且能访问 Hugging Face 官方数据源"
                )
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    process.kill()
                await process.wait()


def extract_control(root: Path, cell: str, output: Path, max_cells: int = 1024) -> None:
    import fsspec
    import h5py
    import numpy as np

    from backend.app.core.registry import AssetRegistry
    from scripts.extract_replogle_k562 import (
        build_anndata,
        decode_categorical,
        decode_strings,
        open_dataset,
        open_group,
        select_registered_hvg,
    )
    from scripts.prepare_context_assets import read_expression_rows, select_control_rows, validate_control

    registry = AssetRegistry(root, root / "data/registry")
    model = registry.model_for(cell)
    registry.verify_entry(model, "gene_list_path", "gene_list_sha256")
    genes = model.path("gene_list_path").read_text(encoding="utf-8").splitlines()
    source = json.loads(
        (Path(__file__).resolve().parents[1] / "resources/inference_assets.json").read_text()
    )["control_source"]
    url = f"hf://datasets/{source['repo']}@{source['revision']}/{source['filename']}"
    filesystem = fsspec.filesystem("hf")

    def emit(message: str) -> None:
        print(json.dumps({"message": message}, ensure_ascii=False), flush=True)

    emit("正在读取固定版本的细胞背景与非靶向标签")
    with filesystem.open(url, "rb", block_size=1024 * 1024) as handle, h5py.File(handle, "r") as atlas:
        obs = open_group(atlas, "obs")
        lines = decode_categorical(open_group(obs, "cell_line"))
        perts = decode_categorical(open_group(obs, "gene"))
        batches = np.asarray(open_dataset(obs, "gem_group"))
        source_genes = decode_strings(open_dataset(atlas, "var/gene_name_index")[:])
        rows = select_control_rows(lines, perts, cell, max_cells=max_cells, seed=source["seed"])
        emit(f"正在范围读取 {len(rows)} 个 {cell} 真实对照细胞")
        barcodes = np.empty(len(lines), dtype=object)
        barcodes[rows] = decode_strings(open_dataset(obs, "cell_barcode")[rows])
        matrix = read_expression_rows(filesystem, url, open_dataset(atlas, "X"), rows)
        frame = build_anndata(
            matrix,
            select_registered_hvg(matrix, source_genes, genes),
            source_genes,
            perts,
            lines,
            batches,
            barcodes,
            rows,
        )
    frame.obs["source_row"] = rows
    frame.uns["celllens_input_provenance"] = {
        "data_kind": "measured",
        "repo": source["repo"],
        "revision": source["revision"],
        "source_file": source["filename"],
        "matrix_slot": "X",
        "sampling_seed": source["seed"],
        "sampling_max_cells": max_cells,
        "processing": "unchanged source expression; ordered HVG column selection only",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    emit("正在校验背景、非靶向标签与基因面板并冻结对照")
    frame.write_h5ad(output, compression="gzip")
    validate_control(output, cell, genes)
    emit(f"已验证 {len(rows)} 个 {cell} 对照细胞")


def watch_parent(pid: int) -> None:
    """Stop this extraction child if its owning API process exits or crashes."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE, read-only process handle.
        if not handle:
            os._exit(1)
        try:
            if kernel.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
                os._exit(1)
        finally:
            kernel.CloseHandle(handle)
    else:
        while os.getppid() == pid:
            time.sleep(1)
        os._exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--cell-line", choices=["K562", "RPE1", "Jurkat", "HepG2"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-cells", type=int, default=1024)
    parser.add_argument("--parent-pid", type=int)
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    output = arguments.output.resolve()
    if not output.is_relative_to(root) or not 1 <= arguments.max_cells <= 1024:
        raise ValueError("Invalid control output or population size")
    if arguments.parent_pid:
        threading.Thread(target=watch_parent, args=(arguments.parent_pid,), daemon=True).start()
    extract_control(root, arguments.cell_line, output, arguments.max_cells)
