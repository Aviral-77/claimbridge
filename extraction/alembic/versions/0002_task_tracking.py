"""task tracking — claims.task_id + claims.stage

Revision ID: 0002_task_tracking
Revises: 0001_initial
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_task_tracking"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("task_id", sa.String(64), nullable=True))
    op.add_column("claims", sa.Column("stage", sa.String(32), nullable=True))
    op.create_index("ix_claims_task_id", "claims", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_claims_task_id", table_name="claims")
    op.drop_column("claims", "stage")
    op.drop_column("claims", "task_id")
