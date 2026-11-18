"""Dataset identities and comparisons are independent of prediction capabilities."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DatasetVersion(FrozenContract):
    id: str
    dataset_id: str
    provider: str
    source: dict[str, Any]
    file: str
    file_sha256: str
    file_md5: str
    file_bytes: int
    expression_slot: str
    expression_scale: str
    gene_identifier: str
    total_cell_count: int
    cell_count: int
    gene_count: int
    species: str
    cell_line: str
    inspection: dict[str, Any]


class Contrast(FrozenContract):
    id: str
    dataset_version_id: str
    label: str
    cell_line: str
    species: str
    perturbation: str
    perturbation_type: str
    dose: str | None = None
    dose_unit: str | None = None
    time: str | None = None
    time_unit: str | None = None
    control_type: str
    control_label: str
    cell_count: int
    control_cell_count: int
    observed_filter: dict[str, str]
    control_filter: dict[str, str]
    sample_count: int | None = None
    biological_replicate_count: int | None = None
    replicate_status: str = "not_verified"
    limitations: list[str] = Field(default_factory=list)


# Estimate multiple float64 work arrays, alignment copies and projections, before
# any densification. Selected cells, not the entire source, enter the engine.
ANALYSIS_MEMORY_BUDGET = 1024 * 1024 * 1024


def check_analysis_budget(control_cells: int, observed_cells: int, genes: int) -> int:
    estimated = (control_cells + observed_cells) * genes * 8 * 4
    if estimated > ANALYSIS_MEMORY_BUDGET:
        raise ValueError("所选细胞与完整基因面板超出 1 GiB 分析矩阵预算；请降低每组 max_cells 后重试")
    return estimated
