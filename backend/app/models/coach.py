"""Coach persistence. No speech/context text or plaintext credentials."""

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CoachPreference(Base):
    __tablename__ = "coach_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class CoachCredential(Base):
    __tablename__ = "coach_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_check: Mapped[str] = mapped_column(String(40), default="not_checked")


class CoachOperatorSession(Base):
    __tablename__ = "coach_operator_sessions"
    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    auth_version: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[float] = mapped_column(Float)


class CoachLedgerRun(Base):
    __tablename__ = "coach_runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    access_digest: Mapped[str] = mapped_column(String(64))
    workout_id: Mapped[int | None] = mapped_column(ForeignKey("workout_sessions.id"), nullable=True, unique=True)
    ledger: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), default="active")
    cap_micros: Mapped[int] = mapped_column(Integer)
    pricing: Mapped[dict] = mapped_column(JSON, default=dict)
    owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    generation: Mapped[int] = mapped_column(Integer, default=0)
    credential_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[float] = mapped_column(Float)


class CoachAttempt(Base):
    __tablename__ = "coach_attempts"
    __table_args__ = (UniqueConstraint("run_id", "opportunity", "stage", "ordinal"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("coach_runs.id"), index=True)
    opportunity: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(16))
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    model: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16))
    reserve_micros: Mapped[int] = mapped_column(Integer)
    cost_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completeness: Mapped[str] = mapped_column(String(16), default="unavailable")
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    pricing: Mapped[dict] = mapped_column(JSON)
    bounds: Mapped[dict] = mapped_column(JSON)
    generation: Mapped[int] = mapped_column(Integer)
    credential_version: Mapped[int] = mapped_column(Integer)
    sent_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[float] = mapped_column(Float)


class CoachReceipt(Base):
    __tablename__ = "coach_receipts"
    __table_args__ = (UniqueConstraint("run_id", "canonical"), UniqueConstraint("run_id", "backend_set_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("coach_runs.id"), index=True)
    canonical: Mapped[str] = mapped_column(String(64))
    backend_set_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(16), default="consumed")


class CoachResponseReceipt(Base):
    __tablename__ = "coach_response_receipts"
    __table_args__ = (UniqueConstraint("attempt_id", "response_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("coach_attempts.id"))
    response_id: Mapped[str] = mapped_column(String(120))
    usage: Mapped[dict] = mapped_column(JSON)


class CoachJob(Base):
    __tablename__ = "coach_jobs"
    __table_args__ = (UniqueConstraint("run_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("coach_runs.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120))
    fingerprint: Mapped[str] = mapped_column(String(64))
    items: Mapped[list] = mapped_column(JSON)
    completed: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(16), default="paused")
    failures: Mapped[int] = mapped_column(Integer, default=0)