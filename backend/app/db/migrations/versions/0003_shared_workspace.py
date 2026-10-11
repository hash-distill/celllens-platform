"""Allow new shared uploads; preserve legacy owned data without publishing it."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_shared_workspace"
down_revision: str | None = "0002_user_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name in ("user_datasets", "user_analyses"):
        with op.batch_alter_table(name) as batch:
            batch.alter_column(
                "owner_id", existing_type=sa.String(40), existing_nullable=False, nullable=True
            )


def downgrade() -> None:
    # Never discard shared rows or silently assign them to an unrelated account.
    for name in ("user_datasets", "user_analyses"):
        if op.get_bind().scalar(sa.text(f"SELECT COUNT(*) FROM {name} WHERE owner_id IS NULL")):
            raise RuntimeError("Shared records exist; export and explicitly migrate them before downgrading.")
    for name in ("user_analyses", "user_datasets"):
        with op.batch_alter_table(name) as batch:
            batch.alter_column(
                "owner_id", existing_type=sa.String(40), existing_nullable=True, nullable=False
            )
