"""Add private user datasets, sessions and downstream analyses."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_user_data"
down_revision: str | None = "0001_runtime_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Match RunStore's SQLite INTEGER primary-key variant for legacy auto IDs.
    # SQLite requires the exact INTEGER spelling for automatic row IDs.
    if op.get_bind().dialect.name == "sqlite":
        for name in ("run_events", "run_artifacts"):
            with op.batch_alter_table(name) as batch:
                batch.alter_column("id", existing_type=sa.BigInteger(), type_=sa.Integer())
    op.create_table(
        "users",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.Column("failed_logins", sa.Integer, nullable=False),
        sa.Column("locked_until", sa.DateTime),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "user_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(40), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False, index=True),
    )
    op.create_table(
        "user_datasets",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("owner_id", sa.String(40), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("metadata_json", sa.JSON, nullable=False),
        sa.Column("summary_json", sa.JSON, nullable=False),
        sa.Column("archived", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_table(
        "user_analyses",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("owner_id", sa.String(40), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("dataset_id", sa.String(40), sa.ForeignKey("user_datasets.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, index=True),
        sa.Column("request_json", sa.JSON, nullable=False),
        sa.Column("artifacts_json", sa.JSON, nullable=False),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    for name in ("user_analyses", "user_datasets", "user_sessions", "users"):
        op.drop_table(name)
    if op.get_bind().dialect.name == "sqlite":
        for name in ("run_events", "run_artifacts"):
            with op.batch_alter_table(name) as batch:
                batch.alter_column("id", existing_type=sa.Integer(), type_=sa.BigInteger())
