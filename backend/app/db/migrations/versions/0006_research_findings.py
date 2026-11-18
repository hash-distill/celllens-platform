"""Persist findings separately from frozen scientific results."""

import sqlalchemy as sa
from alembic import op

revision = "0006_research_findings"
down_revision = "0005_worker_leases"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_findings",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("record_kind", sa.String(16), nullable=False),
        sa.Column("record_id", sa.String(80), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("fingerprint_basis", sa.String(40), nullable=False),
        sa.Column("selection_json", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_findings_record_created", "research_findings", ["record_kind", "record_id", "created_at"]
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM research_findings")):
        raise RuntimeError("Research findings exist; export them before downgrading")
    op.drop_table("research_findings")
