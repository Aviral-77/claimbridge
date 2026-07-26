"""ORM models — the claim store (Phase A2).

Replaces the app_data/*.json filesystem state. Column types are deliberately
portable (JSON, String, Float) so the SAME models run on:
  - SQLite  (bare `uvicorn api:app` on Windows, when DATABASE_URL is unset)
  - Postgres (docker-compose / production)

Denormalized fields (patient_name, uhid, amount, flags, status) let the
Dashboard/Claims lists be a single indexed query instead of reading and parsing
every JSON file — the whole reason to move to a database.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, JSON,
                        String, Text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship)


def _json():
    """JSONB on Postgres (binary, indexable — the scalable store); plain JSON on
    SQLite, which is used only for tests."""
    return JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Claim(Base):
    """One claim = one patient's documents processed into a validated bundle."""

    __tablename__ = "claims"

    # Human-readable reference the clerk sees (CLM-…, CB-…) — also the API path id.
    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    # Multi-tenancy hook: which hospital owns this claim. Defaults to "demo" for
    # now; real tenant scoping arrives with auth (A7).
    hospital_id: Mapped[str] = mapped_column(String(64), index=True, default="demo")

    # Lifecycle: DRAFT | QUEUED | RUNNING | PASS | REVIEW | FAIL  (+ approved flag).
    # QUEUED/RUNNING only get used once processing goes async (A5).
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)

    # Async job tracking: the Celery task id, and the live pipeline stage
    # (queued | reading | extracting | coding | validating | done | failed).
    task_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # --- denormalized for fast list/dashboard queries ---
    patient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    uhid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[float | None] = mapped_column(Float, nullable=True)  # billing.grand_total
    flags: Mapped[int] = mapped_column(Integer, default=0)              # sub-85% review flags

    # --- full payloads (the JSON blobs that used to be separate files) ---
    extraction: Mapped[dict] = mapped_column(_json(), default=dict)
    validation: Mapped[dict | None] = mapped_column(_json(), nullable=True)
    bundle: Mapped[dict | None] = mapped_column(_json(), nullable=True)  # FHIR bundle; set on approve

    # --- processing metadata ---
    seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now)

    documents: Mapped[list["Document"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan",
        order_by="Document.filename")

    def summary(self) -> dict:
        """The shape the Dashboard/Claims list expects (matches the old _summary)."""
        return {
            "id": self.id,
            "patient": self.patient_name,
            "uhid": self.uhid,
            "amount": self.amount,
            "status": "APPROVED" if self.approved else self.status,
            "flags": self.flags or 0,
        }

    def job(self) -> dict:
        """Task-tracking view — status/progress for one processing job."""
        return {
            "task_id": self.task_id,
            "claim_id": self.id,
            "status": "APPROVED" if self.approved else self.status,
            "stage": self.stage,
            "seconds": self.seconds,
            "error": self.error,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Document(Base):
    """A source file uploaded for a claim. Bytes live on disk in A2 (storage_key
    filled in A3 when they move to S3); this table holds the metadata."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    claim_id: Mapped[str] = mapped_column(
        ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)  # S3 key (A3)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    claim: Mapped["Claim"] = relationship(back_populates="documents")
