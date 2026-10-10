import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.core.errors import ScientificContractError
from backend.app.engines.state_se_runner import install_infer_aliases, preserve_signed_se_latents

SOURCE = """
def run_tx_infer(args):
    def clip_array(array):
        np.clip(array, 0, 14, out=array)
    sim_obsm = np.array([-2.0, 1.0])
    clip_array(sim_obsm)
    clip_array(sim_obsm)
    adata = SimpleNamespace(obsm={"latent": np.array([-1.0, 3.0])})
    pred_key = "latent"
    clip_array(adata.obsm[pred_key])
    sim_counts = np.array([-2.0, 20.0])
    clip_array(sim_counts)
    return sim_obsm, adata.obsm[pred_key], sim_counts
"""


def test_latent_patch_keeps_signed_coordinates_and_preserves_expression_clipping():
    code = preserve_signed_se_latents(SOURCE, hashlib.sha256(SOURCE.encode()).hexdigest())
    namespace = {"np": np, "SimpleNamespace": SimpleNamespace}
    exec(code, namespace)
    latent, other, counts = namespace["run_tx_infer"](SimpleNamespace(embed_key="X_state"))
    np.testing.assert_array_equal(latent, [-2, 1])
    np.testing.assert_array_equal(other, [-1, 3])
    np.testing.assert_array_equal(counts, [0, 14])
    latent, other, counts = namespace["run_tx_infer"](SimpleNamespace(embed_key="X_hvg"))
    np.testing.assert_array_equal(latent, [0, 1])
    np.testing.assert_array_equal(other, [0, 3])


def test_unknown_upstream_function_is_rejected():
    with pytest.raises(ScientificContractError, match="fingerprint"):
        preserve_signed_se_latents(SOURCE, "0" * 64)
    modified = SOURCE.replace("    clip_array(sim_obsm)\n", "")
    with pytest.raises(ScientificContractError, match="sites"):
        preserve_signed_se_latents(modified, hashlib.sha256(modified.encode()).hexdigest())


def test_cli_dispatch_aliases_all_use_the_repaired_function():
    def original():
        return "original"

    def repaired():
        return "repaired"
    modules = [SimpleNamespace(run_tx_infer=original) for _ in range(4)]
    install_infer_aliases(original, repaired, modules)
    assert [module.run_tx_infer() for module in modules] == ["repaired"] * 4
