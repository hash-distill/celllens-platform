"""Save figure recipes separately from immutable analysis artifacts."""

import sqlalchemy as sa
from alembic import op

revision = "0007_research_figures"
down_revision = "0006_research_findings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_figures",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("record_kind", sa.String(16), nullable=False),
        sa.Column("record_id", sa.String(80), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("figure_source_sha256", sa.String(64), nullable=False),
        sa.Column("spec_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_figures_record_created", "research_figures", ["record_kind", "record_id", "created_at"]
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM research_figures")):
        raise RuntimeError("Saved figures exist; export them before downgrading")
    op.drop_table("research_figures")
