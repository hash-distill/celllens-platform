"""Extract the model's HVG gene list from var_dims.pkl into the registry gene list.

STATE validates that the output H5AD gene order matches the registered gene list exactly,
so this list must be produced from the model's own saved var_dims rather than guessed.

Usage:
    uv run python scripts/extract_gene_list.py
"""

from __future__ import annotations

import pickle
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VAR_DIMS = PROJECT_ROOT / "models" / "state-replogle-k562" / "var_dims.pkl"
TARGET = PROJECT_ROOT / "data" / "registry" / "state_k562_genes.txt"


def main() -> int:
    with VAR_DIMS.open("rb") as handle:
        var_dims = pickle.load(handle)
    print(f"var_dims type: {type(var_dims).__name__}")
    if isinstance(var_dims, dict):
        print(f"keys: {sorted(var_dims.keys())}")
        for key, value in var_dims.items():
            size = getattr(value, "shape", None) or (len(value) if hasattr(value, "__len__") else "?")
            print(f"  {key}: type={type(value).__name__} size={size}")

    genes = _find_gene_sequence(var_dims)
    if not genes:
        raise SystemExit("Could not locate a gene sequence in var_dims.pkl")

    genes = [str(gene).strip() for gene in genes if str(gene).strip()]
    if len(genes) != len(set(genes)):
        raise SystemExit("Gene list contains duplicates")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text("\n".join(genes) + "\n", encoding="utf-8")
    print(f"\nWrote {len(genes)} genes -> {TARGET.relative_to(PROJECT_ROOT)}")
    print(f"first 10: {genes[:10]}")
    print(f"last 5:   {genes[-5:]}")
    return 0


def _find_gene_sequence(var_dims: object) -> list[str] | None:
    """Locate the gene-name sequence regardless of the exact key it is stored under."""
    if isinstance(var_dims, dict):
        for key in ("genes", "gene_names", "var_names", "hvg", "gene_list", "output_genes"):
            value = var_dims.get(key)
            if _is_str_sequence(value):
                print(f"using key {key!r}")
                return list(value)  # type: ignore[arg-type]
        # Fall back to any long sequence of strings.
        for key, value in var_dims.items():
            if _is_str_sequence(value) and len(value) > 100:  # type: ignore[arg-type]
                print(f"using inferred key {key!r}")
                return list(value)  # type: ignore[arg-type]
    if _is_str_sequence(var_dims):
        return list(var_dims)  # type: ignore[arg-type]
    return None


def _is_str_sequence(value: object) -> bool:
    if isinstance(value, str) or value is None:
        return False
    try:
        items = list(value)  # type: ignore[call-overload]
    except TypeError:
        return False
    return bool(items) and all(isinstance(item, str) for item in items[:50])


if __name__ == "__main__":
    raise SystemExit(main())
