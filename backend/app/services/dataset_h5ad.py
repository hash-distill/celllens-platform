"""Narrow HDF5/AnnData types at the provider boundary, without loading X."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pandas import DataFrame


def read_metadata(handle: Any) -> tuple["DataFrame", "DataFrame"]:
    import h5py
    import pandas as pd
    from anndata.io import read_elem

    frames = []
    for key in ("obs", "var"):
        node = handle[key]
        if not isinstance(node, h5py.Group):
            raise ValueError(f"H5AD {key} 不是元数据组")
        frame = read_elem(node)
        if not isinstance(frame, pd.DataFrame):
            raise ValueError(f"H5AD {key} 不是表格注释")
        frames.append(frame)
    return frames[0], frames[1]


def read_csr(handle: Any, slot: str = "X") -> Any:
    import h5py
    from anndata.io import sparse_dataset

    node = handle[slot]
    if not isinstance(node, h5py.Group) or node.attrs.get("encoding-type") != "csr_matrix":
        raise ValueError("当前 provider 只接受已检查的 CSR 计数矩阵")
    return sparse_dataset(node)
