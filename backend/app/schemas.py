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
    cell_line: Literal["K562", "RPE1", "Jurkat", "HepG2"]
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
    category: str | None = None
    subcategory: str | None = None
    control: float | None = None
    predicted: float | None = None
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


class RunListResponse(StrictModel):
    items: list[RunRecord]
    total: int
    limit: int
    offset: int


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


class TraceScores(StrictModel):
    id: str
    label: str
    control: float | None = None
    predicted: float | None = None
    predicted_delta: float | None = None
    observed_delta: float | None = None


class TraceTask(TraceScores):
    category: str | None = None
    subcategory: str | None = None
    coverage: float = Field(ge=0, le=1)
    evidence_level: Literal["supported", "exploratory", "insufficient"]


class TraceReaction(TraceScores):
    gene_rule: str | None = None
    genes: list[TraceScores]
    total_genes: int = Field(ge=0)
    truncated: bool


class DatabaseProvenance(StrictModel):
    manifest_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    files: dict[str, str]
    source: str | None = None
    organism: str | None = None


class TaskTraceResponse(StrictModel):
    schema_version: Literal[1]
    run_id: str
    database_version: str
    database_provenance: DatabaseProvenance
    task: TraceTask
    reactions: list[TraceReaction]
    relationship_kind: Literal["knowledge_association"]
    determinant_status: Literal["unavailable"]
    determinant_genes: list[str]
    score_units: dict[str, str]
    total_reactions: int = Field(ge=0)
    truncated: bool
    warnings: list[str]
