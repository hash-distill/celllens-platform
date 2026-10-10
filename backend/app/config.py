from functools import lru_cache
from pathlib import Path

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
    gpu_available: bool = False
    state_executable: str = "state"
    log_level: str = "INFO"
    max_projection_points: int = 12_000
    allow_synthetic_results: bool = False
    database_url: str = "mysql+pymysql://celllens:celllens_dev@127.0.0.1:3307/celllens?charset=utf8mb4"
    create_database_schema: bool = False
    worker_id: str = "celllens-worker-1"
    job_lease_seconds: int = 7_200

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
