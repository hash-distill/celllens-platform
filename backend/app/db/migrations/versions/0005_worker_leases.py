"""Durable CPU attempts and observed worker capability heartbeats."""

import sqlalchemy as sa
from alembic import op

revision = "0005_worker_leases"
down_revision = "0004_measured_analyses"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("claim_token", sa.String(40)),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Integer(), nullable=False, server_default="0"),
    ):
        op.add_column("measured_analyses", column)
    op.create_index("ix_measured_analyses_claim_token", "measured_analyses", ["claim_token"])
    op.create_index("ix_measured_analyses_lease_expires_at", "measured_analyses", ["lease_expires_at"])
    op.create_table(
        "measured_attempts",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("analysis_id", sa.String(40), sa.ForeignKey("measured_analyses.id", ondelete="CASCADE")),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_message", sa.Text()),
        sa.UniqueConstraint("analysis_id", "attempt_no", name="uq_measured_attempt"),
    )
    op.create_index("ix_measured_attempts_analysis_id", "measured_attempts", ["analysis_id"])
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(128), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_worker_heartbeats_heartbeat_at", "worker_heartbeats", ["heartbeat_at"])


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM measured_attempts")):
        raise RuntimeError("Export attempt history before downgrading")
    op.drop_table("worker_heartbeats")
    op.drop_table("measured_attempts")
    with op.batch_alter_table("measured_analyses") as batch:
        batch.drop_index("ix_measured_analyses_claim_token")
        batch.drop_index("ix_measured_analyses_lease_expires_at")
        for name in (
            "claim_token",
            "worker_id",
            "lease_expires_at",
            "heartbeat_at",
            "attempt_no",
            "cancel_requested",
        ):
            batch.drop_column(name)
