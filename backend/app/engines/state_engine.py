import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from backend.app.core.errors import AssetNotReadyError, StateInferenceError
from backend.app.core.registry import RegistryEntry


@dataclass(frozen=True)
class StateRunInput:
    cell_line: str
    perturbation: str
    control_path: Path
    n_cells: int
    seed: int


class StateCliEngine:
    def __init__(
        self,
        executable: str = "state",
        timeout_seconds: int = 3600,
        *,
        device: str = "cpu",
    ):
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.device = device

    def perturbation_label(self, perturbation: str, model: RegistryEntry) -> str:
        import torch

        mapping_path = model.path("model_dir") / "pert_onehot_map.pt"
        if not mapping_path.is_file():
            raise AssetNotReadyError(f"STATE perturbation vocabulary does not exist: {mapping_path}")
        mapping = torch.load(mapping_path, map_location="cpu", weights_only=False)
        matches = {str(key) for key in mapping if str(key).strip().upper() == perturbation.strip().upper()}
        if len(matches) != 1:
            raise StateInferenceError(
                "Requested perturbation is missing or ambiguous in the model vocabulary"
            )
        return matches.pop()

    def build_command(
        self,
        request: StateRunInput,
        model: RegistryEntry,
        output_path: Path,
        perturbation_tsv: Path,
    ) -> list[str]:
        payload = model.payload
        prefix = (
            [sys.executable, "-m", "backend.app.engines.state_gpu_runner"]
            if self.device == "cuda"
            else [self.executable]
        )
        command = [
            *prefix,
            "tx",
            "infer",
            "--model-dir",
            str(model.path("model_dir")),
            "--checkpoint",
            str(model.path("checkpoint_path")),
            "--adata",
            str(request.control_path),
            "--pert-col",
            str(payload["perturbation_column"]),
            "--output",
            str(output_path),
            "--seed",
            str(request.seed),
            "--tsv",
            str(perturbation_tsv),
            "--max-cells",
            str(request.n_cells),
        ]
        if embed_key := payload.get("embed_key"):
            command.extend(["--embed-key", str(embed_key)])
        if cell_type_column := payload.get("cell_type_column"):
            command.extend(
                ["--celltype-col", str(cell_type_column), "--celltypes", request.cell_line.lower()]
            )
        if control_perturbation := payload.get("control_perturbation"):
            command.extend(["--control-pert", str(control_perturbation)])
        return command

    def infer(self, request: StateRunInput, model: RegistryEntry, output_path: Path) -> Path:
        for path in (request.control_path, model.path("model_dir"), model.path("checkpoint_path")):
            if not path.exists():
                raise AssetNotReadyError(f"STATE input asset does not exist: {path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        perturbation_tsv = output_path.with_suffix(".perturbations.tsv")
        perturbation_label = self.perturbation_label(request.perturbation, model)
        perturbation_tsv.write_text(
            f"perturbation\tnum_cells\n{perturbation_label}\t{request.n_cells}\n",
            encoding="utf-8",
        )
        command = self.build_command(request, model, output_path, perturbation_tsv)
        command_log = output_path.with_suffix(".command.json")
        command_log.write_text(json.dumps(command, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StateInferenceError(f"Unable to execute STATE: {exc}") from exc
        output_path.with_suffix(".stdout.log").write_text(completed.stdout[-20_000:], encoding="utf-8")
        output_path.with_suffix(".stderr.log").write_text(completed.stderr[-20_000:], encoding="utf-8")
        if completed.returncode != 0:
            raise StateInferenceError(completed.stderr[-4000:] or f"STATE exited with {completed.returncode}")
        if "using control fallback one-hot" in completed.stdout:
            raise StateInferenceError("STATE used a control fallback for an unmapped perturbation")
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise StateInferenceError("STATE finished without a non-empty output H5AD")
        try:
            import anndata as ad
        except ImportError as exc:
            raise StateInferenceError("Install the 'model' extra to validate STATE output") from exc
        try:
            output = ad.read_h5ad(output_path)
            validate_state_output(output, request, model)
            output.write_h5ad(output_path)
        except StateInferenceError:
            raise
        except Exception as exc:
            raise StateInferenceError(f"Cannot validate STATE output: {exc}") from exc
        return output_path


def validate_state_output(output: Any, request: StateRunInput, model: RegistryEntry) -> None:
    if output.n_obs < 1 or output.n_vars < 1:
        raise StateInferenceError("STATE output is empty")
    matrix = output.X.toarray() if hasattr(output.X, "toarray") else np.asarray(output.X)
    if not np.isfinite(matrix).all():
        raise StateInferenceError("STATE output contains non-finite expression values")
    if matrix.shape != (output.n_obs, output.n_vars):
        raise StateInferenceError("STATE output expression dimensions do not match AnnData shape")

    cell_type_column = model.payload.get("cell_type_column")
    if cell_type_column:
        if cell_type_column not in output.obs:
            raise StateInferenceError("STATE output is missing the registered cell background column")
        backgrounds = {str(value).strip().lower() for value in output.obs[cell_type_column]}
        if backgrounds != {request.cell_line.lower()}:
            raise StateInferenceError("STATE output cell background differs from the requested background")

    perturbation_column = model.payload.get("perturbation_column")
    if perturbation_column:
        if perturbation_column not in output.obs:
            raise StateInferenceError(f"STATE output is missing obs[{perturbation_column!r}]")
        labels = {str(value).upper() for value in output.obs[perturbation_column].dropna()}
        if request.perturbation.upper() not in labels:
            raise StateInferenceError("STATE output does not contain the requested perturbation label")

    gene_list_value = model.payload.get("gene_list_path")
    if gene_list_value:
        gene_list_path = model.path("gene_list_path")
        if not gene_list_path.is_file():
            raise AssetNotReadyError(f"STATE gene list does not exist: {gene_list_path}")
        expected = [
            line.strip().upper()
            for line in gene_list_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        actual = [str(gene).strip().upper() for gene in output.var_names]
        embed_key = model.payload.get("embed_key")
        if embed_key:
            # The registered gene list describes the *predicted panel*. For embed_key
            # models STATE writes predictions into obsm[embed_key] and leaves the
            # original var_names untouched, so the panel cannot be compared against
            # var_names order. Verify the prediction width and that every panel gene
            # still exists in the output instead.
            _validate_prediction_panel(output, embed_key, expected, actual)
        elif actual != expected:
            raise StateInferenceError("STATE output gene order does not match the registered model gene list")

    output.uns["celllens_provenance"] = {
        "model_id": str(model.payload.get("id", "unknown")),
        "cell_line": request.cell_line,
        "perturbation": request.perturbation,
        "seed": request.seed,
        "requested_cells": request.n_cells,
    }


def _validate_prediction_panel(
    output: Any,
    embed_key: str,
    expected: list[str],
    var_names: list[str],
) -> None:
    """Check that obsm[embed_key] is a finite matrix over exactly the registered panel."""
    if embed_key not in output.obsm:
        raise StateInferenceError(
            f"STATE output is missing obsm[{embed_key!r}], which the model registers as its prediction space"
        )
    matrix = output.obsm[embed_key]
    if getattr(matrix, "shape", (0, 0))[1] != len(expected):
        raise StateInferenceError(
            f"STATE output obsm[{embed_key!r}] has {getattr(matrix, 'shape', None)} columns "
            f"but the registered panel has {len(expected)} genes"
        )
    values = matrix.toarray() if hasattr(matrix, "toarray") else np.asarray(matrix)
    if not np.isfinite(values).all():
        raise StateInferenceError(f"STATE output obsm[{embed_key!r}] contains non-finite values")
    present = set(var_names)
    missing = [gene for gene in expected if gene not in present]
    if missing:
        raise StateInferenceError(
            f"STATE output is missing {len(missing)} registered panel genes, e.g. {missing[:5]}"
        )
