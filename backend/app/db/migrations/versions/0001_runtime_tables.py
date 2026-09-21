"""Create durable CellLens runtime tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_runtime_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("run_id", sa.String(40), primary_key=True),
        sa.Column("mode", sa.String(24), nullable=False),
        sa.Column("cell_line", sa.String(32), nullable=False),
        sa.Column("perturbation", sa.String(64), nullable=False),
        sa.Column("n_cells", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("stage_progress", sa.Integer(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.Text()),
        sa.Column("cache_key", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_cache_key", "runs", ["cache_key"])
    op.create_index("ix_runs_status_updated", "runs", ["status", "updated_at"])
    op.create_index("ix_runs_cell_perturbation", "runs", ["cell_line", "perturbation"])

    op.create_table(
        "run_attempts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(64)),
        sa.UniqueConstraint("run_id", "attempt_no", name="uq_run_attempt"),
    )
    op.create_index("ix_run_attempts_run_id", "run_attempts", ["run_id"])
    op.create_index("ix_run_attempts_worker_id", "run_attempts", ["worker_id"])
    op.create_index("ix_run_attempts_lease_expires_at", "run_attempts", ["lease_expires_at"])

    op.create_table(
        "run_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(32)),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("stage_progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])

    op.create_table(
        "run_artifacts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("relative_path", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "kind", name="uq_run_artifact_kind"),
    )
    op.create_index("ix_run_artifacts_run_id", "run_artifacts", ["run_id"])

    op.create_table(
        "run_cache",
        sa.Column("cache_key", sa.String(64), primary_key=True),
        sa.Column("run_id", sa.String(40), sa.ForeignKey("runs.run_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("run_cache")
    op.drop_index("ix_run_artifacts_run_id", table_name="run_artifacts")
    op.drop_table("run_artifacts")
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_table("run_events")
    op.drop_index("ix_run_attempts_lease_expires_at", table_name="run_attempts")
    op.drop_index("ix_run_attempts_worker_id", table_name="run_attempts")
    op.drop_index("ix_run_attempts_run_id", table_name="run_attempts")
    op.drop_table("run_attempts")
    op.drop_index("ix_runs_cell_perturbation", table_name="runs")
    op.drop_index("ix_runs_status_updated", table_name="runs")
    op.drop_index("ix_runs_cache_key", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_table("runs")
