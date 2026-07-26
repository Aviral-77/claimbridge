"""auth — hospitals + users

Revision ID: 0003_auth
Revises: 0002_task_tracking
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_auth"
down_revision = "0002_task_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hospitals",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("hospital_id", sa.String(64), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["hospital_id"], ["hospitals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_hospital_id", "users", ["hospital_id"])


def downgrade() -> None:
    op.drop_index("ix_users_hospital_id", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("hospitals")
