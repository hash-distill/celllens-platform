"""Independent measured public-data analyses; preserve prediction history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_measured_analyses"
down_revision: str | None = "0003_shared_workspace"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "measured_analyses",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("cell_line", sa.String(32), nullable=False),
        sa.Column("perturbation", sa.String(64), nullable=False),
        sa.Column("max_cells", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("manifest_sha256", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_measured_status_updated", "measured_analyses", ["status", "updated_at"])


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM measured_analyses")):
        raise RuntimeError("Measured history exists; explicitly export it before downgrading")
    op.drop_table("measured_analyses")
