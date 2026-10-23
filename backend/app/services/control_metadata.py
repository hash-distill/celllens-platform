"""Read the registered control population from obs without loading expression or weights."""

from typing import Any

from backend.app.core.errors import CellLensError


def control_cell_count(registry: Any, cell_line: str) -> int | None:
    try:
        dataset = registry.dataset_for(cell_line, require_enabled=False)
        if not dataset.enabled or not registry.asset_is_valid_cached(
            dataset, "control_path", "control_sha256"
        ):
            return None
        import h5py

        with h5py.File(dataset.path("control_path"), "r") as handle:
            obs = handle["obs"]
            if not isinstance(obs, h5py.Group):
                return None
            index_key = obs.attrs["_index"]
            if isinstance(index_key, bytes):
                index_key = index_key.decode("utf-8")
            index = obs[index_key]
            if not isinstance(index, h5py.Dataset) or index.ndim != 1:
                return None
            count = len(index)
            if count < 1:
                return None

            def labels(name: str) -> set[str]:
                column = obs[name]
                if isinstance(column, h5py.Group):
                    categories_dataset, codes_dataset = column["categories"], column["codes"]
                    if (
                        not isinstance(categories_dataset, h5py.Dataset)
                        or not isinstance(codes_dataset, h5py.Dataset)
                        or categories_dataset.ndim != 1
                        or codes_dataset.ndim != 1
                    ):
                        raise ValueError("Invalid categorical observation metadata")
                    categories = categories_dataset.asstr()[:]
                    codes = codes_dataset[:]
                    if len(codes) != count or any(code < 0 or code >= len(categories) for code in codes):
                        raise ValueError("Missing or invalid control observation labels")
                    values = categories[codes]
                elif isinstance(column, h5py.Dataset) and column.ndim == 1:
                    values = column.asstr()[:]
                    if len(values) != count:
                        raise ValueError("Control observation labels have the wrong size")
                else:
                    raise ValueError("Invalid observation label dataset")
                return {str(value).strip().lower() for value in values}

            if labels("gene") != {"non-targeting"} or labels("cell_line") != {cell_line.lower()}:
                return None
        return count if registry.asset_is_valid_cached(dataset, "control_path", "control_sha256") else None
    except (CellLensError, ImportError, OSError, KeyError, TypeError, ValueError):
        return None
