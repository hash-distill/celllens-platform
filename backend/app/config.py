from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CELLLENS_",
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
    )

    project_root: Path = PROJECT_ROOT
    api_prefix: str = "/api/v1"
    worker_enabled: bool = False
    worker_mode: Literal["external", "embedded", "disabled"] = "external"
    worker_poll_seconds: float = Field(default=2.0, ge=0.1, le=60)
    worker_heartbeat_seconds: int = Field(default=10, ge=1, le=60)
    worker_stale_seconds: int = Field(default=45, ge=5, le=300)
    deployment_mode: Literal["local", "private", "public"] = "local"
    workspace_token: str = Field(default="", repr=False)
    public_result_ids: str = ""
    session_secure_cookie: bool = True
    controlled_import_enabled: bool = False
    controlled_import_root: Path | None = None
    controlled_import_max_bytes: int = 268_435_456
    h5ad_upload_enabled: bool = True
    h5ad_upload_max_bytes: int = Field(default=268_435_456, ge=1, le=1_073_741_824)
    h5ad_upload_max_total_bytes: int = Field(default=1_073_741_824, ge=1)
    h5ad_upload_ttl_seconds: int = Field(default=86_400, ge=60, le=604_800)
    h5ad_upload_timeout_seconds: int = Field(default=300, ge=1, le=3600)
    gpu_available: bool = False
    state_executable: str = "state"
    log_level: str = "INFO"
    max_projection_points: int = 12_000
    allow_synthetic_results: bool = False
    database_url: str = "mysql+pymysql://celllens:celllens_dev@127.0.0.1:3307/celllens?charset=utf8mb4"
    create_database_schema: bool = False
    worker_id: str = "celllens-worker-1"
    job_lease_seconds: int = Field(default=120, ge=10, le=86_400)
    assistant_extra_origins: str = ""
    assistant_timeout_seconds: int = Field(default=300, ge=5, le=600)

    @property
    def registry_root(self) -> Path:
        return self.project_root / "data" / "registry"

    @property
    def derived_root(self) -> Path:
        return self.project_root / "data" / "derived" / "runs"

    @property
    def demo_root(self) -> Path:
        return self.project_root / "data" / "demo"

    @property
    def sccellfie_database_root(self) -> Path:
        return self.project_root / "data" / "registry" / "sccellfie" / "human"

    @property
    def gene_identity_root(self) -> Path:
        return self.registry_root / "gene_identity"


@lru_cache
def get_settings() -> Settings:
    return Settings()
