import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from backend.app.core.errors import StateInferenceError
from backend.app.core.registry import RegistryEntry
from backend.app.engines.state_engine import StateCliEngine, StateRunInput, validate_state_output


def test_state_command_uses_official_infer_boundary(tmp_path: Path):
    model = RegistryEntry(
        {
            "id": "test",
            "model_dir": "model",
            "checkpoint_path": "model/checkpoints/final.ckpt",
            "perturbation_column": "target_gene",
            "embed_key": "X_hvg",
            "cell_type_column": "cell_type",
            "control_perturbation": "non-targeting",
        },
        tmp_path,
    )
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 512, 42)
    command = StateCliEngine("state").build_command(
        request,
        model,
        tmp_path / "predicted.h5ad",
        tmp_path / "perturbations.tsv",
    )
    assert command[:3] == ["state", "tx", "infer"]
    assert command[command.index("--pert-col") + 1] == "target_gene"
    assert command[command.index("--embed-key") + 1] == "X_hvg"
    assert command[command.index("--celltypes") + 1] == "k562"
    assert command[command.index("--max-cells") + 1] == "512"


def test_state_command_uses_gpu_runner_when_cuda_is_requested(tmp_path: Path):
    model = RegistryEntry(
        {
            "id": "test",
            "model_dir": "model",
            "checkpoint_path": "model/checkpoints/final.ckpt",
            "perturbation_column": "gene",
        },
        tmp_path,
    )
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 64, 42)

    command = StateCliEngine("state", device="cuda").build_command(
        request,
        model,
        tmp_path / "predicted.h5ad",
        tmp_path / "perturbations.tsv",
    )

    assert command[:5] == [sys.executable, "-m", "backend.app.engines.state_gpu_runner", "tx", "infer"]


class FakeAnnData:
    def __init__(self, *, matrix=None, perturbations=None, obsm=None, var_names=None):
        self.X = np.asarray(matrix if matrix is not None else [[1.0, 2.0]])
        self.n_obs, self.n_vars = self.X.shape
        self.var_names = pd.Index(var_names if var_names is not None else ["A", "B"])
        self.obs = pd.DataFrame({"target_gene": perturbations or ["MYC"]})
        self.obsm = obsm if obsm is not None else {}
        self.uns = {}


def test_state_output_contract_rejects_non_finite_values(tmp_path: Path):
    model = RegistryEntry({"id": "test", "perturbation_column": "target_gene"}, tmp_path)
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 1, 42)
    with pytest.raises(StateInferenceError, match="non-finite"):
        validate_state_output(FakeAnnData(matrix=[[1.0, np.nan]]), request, model)


def test_state_output_contract_records_provenance(tmp_path: Path):
    model = RegistryEntry({"id": "state-v1", "perturbation_column": "target_gene"}, tmp_path)
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 1, 42)
    output = FakeAnnData()
    validate_state_output(output, request, model)
    assert output.uns["celllens_provenance"]["model_id"] == "state-v1"


def test_state_output_rejects_a_different_cell_background(tmp_path: Path):
    model = RegistryEntry(
        {"id": "rpe1", "perturbation_column": "target_gene", "cell_type_column": "cell_line"}, tmp_path
    )
    request = StateRunInput("RPE1", "MYC", tmp_path / "control.h5ad", 1, 42)
    output = FakeAnnData()
    output.obs["cell_line"] = ["k562"]
    with pytest.raises(StateInferenceError, match="background"):
        validate_state_output(output, request, model)


def test_cli_perturbation_preserves_official_mixed_case_vocabulary(tmp_path: Path):
    import torch

    engine = StateCliEngine()
    assert hasattr(engine, "perturbation_label"), "official vocabulary resolution is missing"
    torch.save({"C1orf43": torch.ones(2), "AAMP": torch.zeros(2)}, tmp_path / "pert_onehot_map.pt")
    model = RegistryEntry({"model_dir": "."}, tmp_path)
    assert engine.perturbation_label("C1ORF43", model) == "C1orf43"
    assert engine.perturbation_label("AAMP", model) == "AAMP"
    with pytest.raises(StateInferenceError, match="vocabulary"):
        engine.perturbation_label("UNKNOWN", model)


def test_embed_key_model_validates_prediction_panel_not_var_names(tmp_path: Path):
    """The registered gene list describes obsm[embed_key], not the full var_names axis.

    STATE keeps the original var_names (all genes) in its output while writing the
    predicted panel into obsm[embed_key], so comparing the panel against var_names
    order would reject every legitimate embed_key run.
    """
    gene_list = tmp_path / "genes.txt"
    gene_list.write_text("A\nB\n", encoding="utf-8")
    model = RegistryEntry(
        {
            "id": "state-v1",
            "perturbation_column": "target_gene",
            "gene_list_path": "genes.txt",
            "embed_key": "X_hvg",
        },
        tmp_path,
    )
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 1, 42)
    output = FakeAnnData(obsm={"X_hvg": np.array([[0.5, 0.25]])}, var_names=["A", "B", "C"])
    validate_state_output(output, request, model)
    assert output.uns["celllens_provenance"]["perturbation"] == "MYC"


def test_embed_key_model_rejects_wrong_prediction_width(tmp_path: Path):
    gene_list = tmp_path / "genes.txt"
    gene_list.write_text("A\nB\n", encoding="utf-8")
    model = RegistryEntry(
        {
            "id": "state-v1",
            "perturbation_column": "target_gene",
            "gene_list_path": "genes.txt",
            "embed_key": "X_hvg",
        },
        tmp_path,
    )
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 1, 42)
    output = FakeAnnData(obsm={"X_hvg": np.array([[0.5, 0.25, 0.1]])}, var_names=["A", "B", "C"])
    with pytest.raises(StateInferenceError, match="registered panel"):
        validate_state_output(output, request, model)


def test_embed_key_model_rejects_missing_panel_slot(tmp_path: Path):
    gene_list = tmp_path / "genes.txt"
    gene_list.write_text("A\nB\n", encoding="utf-8")
    model = RegistryEntry(
        {
            "id": "state-v1",
            "perturbation_column": "target_gene",
            "gene_list_path": "genes.txt",
            "embed_key": "X_hvg",
        },
        tmp_path,
    )
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 1, 42)
    with pytest.raises(StateInferenceError, match="missing obsm"):
        validate_state_output(FakeAnnData(), request, model)


def test_latent_input_can_have_separate_expression_output_slot(tmp_path: Path):
    (tmp_path / "genes.txt").write_text("A\nB\n")
    model = RegistryEntry(
        {"id": "se-full", "gene_list_path": "genes.txt", "embed_key": "X_state", "expression_key": "X"},
        tmp_path,
    )
    output = FakeAnnData(var_names=["A", "B"], obsm={"X_state": np.ones((1, 2058))})
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 1, 42)
    validate_state_output(output, request, model)


@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_se_command_uses_signed_latent_runner_on_either_device(tmp_path: Path, device):
    model = RegistryEntry(
        {
            "model_dir": "model",
            "checkpoint_path": "model/best.ckpt",
            "perturbation_column": "gene",
            "embed_key": "X_state",
            "expression_key": "X",
        },
        tmp_path,
    )
    request = StateRunInput("K562", "MYC", tmp_path / "control.h5ad", 64, 42)
    command = StateCliEngine(device=device).build_command(
        request, model, tmp_path / "predicted.h5ad", tmp_path / "perts.tsv"
    )
    assert command[:3] == [sys.executable, "-m", "backend.app.engines.state_se_runner"]
    assert command[command.index("--celllens-device") + 1] == device
