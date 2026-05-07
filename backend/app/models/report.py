"""Cached WCL report + per-fight + per-player rollups.

We don't store the full event stream — just enough to drive the AI analysis
and the comparison UI: fights, players, totals, gear, key cast counts.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("wcl_code", name="uq_reports_wcl_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    wcl_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zone_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    region: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    game_version: Mapped[str] = mapped_column(String(16), default="retail", nullable=False)
    raw_meta: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    fights: Mapped[list["ReportFight"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", lazy="selectin"
    )


class ReportFight(Base):
    __tablename__ = "report_fights"
    __table_args__ = (
        UniqueConstraint("report_id", "fight_id", name="uq_report_fights_report_fight"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fight_id: Mapped[int] = mapped_column(Integer, nullable=False)  # WCL fight index within report
    encounter_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)  # WCL difficulty code
    keystone_level: Mapped[int | None] = mapped_column(Integer, nullable=True)  # M+ keystone
    is_kill: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    boss_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    report: Mapped[Report] = relationship(back_populates="fights")
    players: Mapped[list["ReportPlayer"]] = relationship(
        back_populates="fight", cascade="all, delete-orphan", lazy="selectin"
    )


class ReportPlayer(Base):
    __tablename__ = "report_players"
    __table_args__ = (
        Index("ix_report_players_spec", "spec_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fight_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_fights.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    server: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    class_slug: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    spec_slug: Mapped[str] = mapped_column(String(48), nullable=False)
    role: Mapped[str] = mapped_column(String(8), nullable=False)  # dps/healer/tank
    item_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    dps: Mapped[float | None] = mapped_column(Float, nullable=True)
    hps: Mapped[float | None] = mapped_column(Float, nullable=True)
    damage_done: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    healing_done: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    deaths: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    talents_loadout: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    extras: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    fight: Mapped[ReportFight] = relationship(back_populates="players")
    casts: Mapped[list["ReportPlayerCast"]] = relationship(
        back_populates="player", cascade="all, delete-orphan", lazy="selectin"
    )
    gear: Mapped[list["ReportPlayerGear"]] = relationship(
        back_populates="player", cascade="all, delete-orphan", lazy="selectin"
    )


class ReportPlayerCast(Base):
    __tablename__ = "report_player_casts"
    __table_args__ = (
        UniqueConstraint("player_id", "ability_id", name="uq_report_player_casts_player_ability"),
        Index("ix_report_player_casts_ability", "ability_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ability_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ability_name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    casts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)

    player: Mapped[ReportPlayer] = relationship(back_populates="casts")


class ReportPlayerGear(Base):
    __tablename__ = "report_player_gear"
    __table_args__ = (
        UniqueConstraint("player_id", "slot", name="uq_report_player_gear_player_slot"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("report_players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slot: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=head ... 16=offhand
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    item_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(128), default="", nullable=False)
    icon: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enchant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gem_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)
    bonus_ids: Mapped[list[int]] = mapped_column(JSONB, default=list, nullable=False)

    player: Mapped[ReportPlayer] = relationship(back_populates="gear")
