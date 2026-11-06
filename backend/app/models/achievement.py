"""Persistent, idempotent achievement definitions, progress, grants and evaluation outbox."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AchievementDefinition(Base):
    __tablename__ = "achievement_definitions"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    rules_version: Mapped[str] = mapped_column(String(80), nullable=False)
    content_version: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)


class AchievementProgress(TimestampMixin, Base):
    __tablename__ = "achievement_progress"
    __table_args__ = (UniqueConstraint("user_id", "definition_id", "scope_key", name="uq_achievement_progress_scope"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    definition_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    scope_key: Mapped[str] = mapped_column(String(160), default="lifetime", nullable=False)
    current_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    highest_tier: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    data_state: Mapped[str] = mapped_column(String(32), default="available", nullable=False)
    computed_through: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AchievementGrant(TimestampMixin, Base):
    __tablename__ = "achievement_grants"
    __table_args__ = (UniqueConstraint("user_id", "definition_id", "tier", "scope_key", name="uq_achievement_grant"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    definition_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_key: Mapped[str] = mapped_column(String(160), default="lifetime", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="earned", nullable=False)
    source_workout_id: Mapped[int | None] = mapped_column(ForeignKey("workout_sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    earned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class AchievementEvidence(Base):
    __tablename__ = "achievement_evidence"
    __table_args__ = (UniqueConstraint("grant_id", "source_type", "source_id", name="uq_achievement_evidence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("achievement_grants.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)


class AchievementOutbox(Base):
    __tablename__ = "achievement_outbox"
    __table_args__ = (UniqueConstraint("user_id", "source_type", "source_id", "source_revision", name="uq_achievement_outbox"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AchievementReceipt(Base):
    __tablename__ = "achievement_receipts"
    __table_args__ = (UniqueConstraint("user_id", "grant_id", "surface", name="uq_achievement_receipt"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("achievement_grants.id", ondelete="CASCADE"), nullable=False, index=True)
    surface: Mapped[str] = mapped_column(String(32), nullable=False)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
