"""Run STATE's official CLI while placing its inference model on CUDA.

arc-state 0.11.1 does not expose a device flag for ``state tx infer`` and leaves
the Lightning checkpoint on CPU. This narrow adapter preserves the official CLI
arguments and output contract while moving the loaded model to CUDA.
"""

from __future__ import annotations

from typing import Any

import torch


def main() -> None:
    if not torch.cuda.is_available():
        raise SystemExit("CUDA was requested for STATE inference, but torch.cuda.is_available() is false")

    from state.tx.models.state_transition import StateTransitionPerturbationModel

    original_loader = StateTransitionPerturbationModel.load_from_checkpoint

    def load_on_cuda(*args: Any, **kwargs: Any) -> Any:
        return original_loader(*args, **kwargs).to("cuda")

    StateTransitionPerturbationModel.load_from_checkpoint = load_on_cuda

    from state.__main__ import main as state_main

    state_main()


if __name__ == "__main__":
    main()
