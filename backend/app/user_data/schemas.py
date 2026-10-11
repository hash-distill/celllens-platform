from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UploadMetadata(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    expression_scale: Literal["raw_counts", "cp10k", "log1p_cp10k"]
    input_layer: str = Field(default="X", min_length=1, max_length=128)
    matrix_scope: Literal["full_library", "selected_panel"] = "selected_panel"
    total_counts_key: str | None = Field(default=None, max_length=128)
    organism: Literal["human"] = "human"
    cell_context: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def nonempty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("数据集名称不能为空")
        return value.strip()


class AnalysisRequest(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    dataset_id: str = Field(pattern=r"^ds_[a-f0-9]{32}$")
    kind: Literal["explore", "metabolism"] = "explore"
    group_key: str | None = Field(default=None, max_length=128)
    reference_group: str | None = Field(default=None, max_length=256)
    seed: int = Field(default=42, ge=0, le=2**32 - 1)
