"""initial schema — claims + documents

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("hospital_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("patient_name", sa.String(255), nullable=True),
        sa.Column("uhid", sa.String(64), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("flags", sa.Integer(), nullable=False),
        sa.Column("extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("bundle", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("seconds", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_claims_hospital_id", "claims", ["hospital_id"])
    op.create_index("ix_claims_status", "claims", ["status"])

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("claim_id", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=True),
        sa.Column("storage_key", sa.String(1024), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["claim_id"], ["claims.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_claim_id", "documents", ["claim_id"])


def downgrade() -> None:
    op.drop_index("ix_documents_claim_id", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_claims_status", table_name="claims")
    op.drop_index("ix_claims_hospital_id", table_name="claims")
    op.drop_table("claims")
