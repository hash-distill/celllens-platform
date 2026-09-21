from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RunStatus(StrEnum):
    QUEUED = "queued"
    STATE_RUNNING = "state_running"
    ADAPTING = "adapting"
    METABOLIC_RUNNING = "metabolic_running"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"


class CreateRunRequest(StrictModel):
    cell_line: Literal["K562", "RPE1"]
    perturbation: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    mode: Literal["online", "precomputed", "validation"] = "online"
    n_cells: int = Field(default=512, ge=64, le=4096)
    seed: int = Field(default=42, ge=0, le=2_147_483_647)

    @field_validator("perturbation")
    @classmethod
    def normalize_perturbation(cls, value: str) -> str:
        return value.strip().upper()


class CoverageSummary(StrictModel):
    state_gene_fraction: float = Field(ge=0, le=1)
    metabolic_gene_fraction: float = Field(ge=0, le=1)
    reaction_fraction: float = Field(ge=0, le=1)
    supported_tasks: int = Field(ge=0)
    exploratory_tasks: int = Field(ge=0)
    insufficient_tasks: int = Field(ge=0)


class EvidenceItem(StrictModel):
    id: str
    label: str
    predicted_delta: float
    observed_delta: float | None = None
    coverage: float = Field(ge=0, le=1)
    evidence_level: Literal["supported", "exploratory", "insufficient"]
    determinant_genes: list[str] = Field(default_factory=list)


class RunRecord(StrictModel):
    run_id: str
    status: RunStatus
    stage_progress: int = Field(ge=0, le=100)
    request: CreateRunRequest
    created_at: datetime
    updated_at: datetime
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None


class CreateRunResponse(StrictModel):
    run_id: str
    status: RunStatus
    cache_hit: bool


class RunSummary(StrictModel):
    run_id: str
    status: RunStatus
    stage_progress: int = Field(ge=0, le=100)
    cell_line: str
    perturbation: str
    coverage: CoverageSummary | None = None
    top_genes: list[EvidenceItem] = Field(default_factory=list)
    metabolic_tasks: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None


class ContextItem(StrictModel):
    cell_line: str
    online_ready: bool
    validation_ready: bool
    precomputed_ready: bool
    model_id: str | None
    disabled_reason: str | None = None
    readiness_reasons: list[str] = Field(default_factory=list)
