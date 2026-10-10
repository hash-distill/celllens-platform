"""Run pinned official inference while preserving signed SE latent outputs."""

import argparse
import ast
import hashlib
import inspect
import sys
from typing import Any

from backend.app.core.errors import ScientificContractError

OFFICIAL_INFER_SHA256 = "778a6b6773b8dc4b86f3f67bc51d1adf46f30f18ca51e6d6b3d89b98ae17ae8f"


def install_infer_aliases(original: Any, repaired: Any, modules: list[Any]) -> None:
    if any(module.run_tx_infer is not original for module in modules):
        raise ScientificContractError("Official inference dispatch aliases changed; review adapter")
    for module in modules:
        module.run_tx_infer = repaired


def preserve_signed_se_latents(source: str, expected_sha256: str) -> str:
    if hashlib.sha256(source.encode()).hexdigest() != expected_sha256:
        raise ScientificContractError("Official STATE inference fingerprint changed; review adapter")

    class ClipGuard(ast.NodeTransformer):
        changed = 0

        def visit_Expr(self, node):
            call = node.value
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "clip_array"
                and len(call.args) == 1
            ):
                argument = ast.unparse(call.args[0])
                if argument in {"sim_obsm", "adata.obsm[pred_key]"}:
                    self.changed += 1
                    condition = ast.parse("args.embed_key == 'X_hvg'", mode="eval").body
                    return ast.copy_location(ast.If(test=condition, body=[node], orelse=[]), node)
            return node

    transformer = ClipGuard()
    tree = transformer.visit(ast.parse(source))
    if transformer.changed != 3:
        raise ScientificContractError("Official STATE latent clipping sites changed; review adapter")
    return ast.unparse(ast.fix_missing_locations(tree))


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--celllens-device", choices=("cpu", "cuda"), default="cuda")
    options, remaining = parser.parse_known_args()
    sys.argv = [sys.argv[0], *remaining]
    from state import __main__ as entry
    from state import _cli
    from state._cli import _tx
    from state._cli._tx import _infer

    source = inspect.getsource(_infer.run_tx_infer)
    patched = preserve_signed_se_latents(source, OFFICIAL_INFER_SHA256)
    namespace = dict(vars(_infer))
    exec(compile(patched, "celllens_signed_se_inference", "exec"), namespace)
    install_infer_aliases(_infer.run_tx_infer, namespace["run_tx_infer"], [_infer, _tx, _cli, entry])
    if options.celllens_device == "cuda":
        from backend.app.engines.state_gpu_runner import main as gpu_main

        gpu_main()
    else:
        from state.__main__ import main as state_main

        state_main()


if __name__ == "__main__":
    main()
