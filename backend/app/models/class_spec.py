"""Static lookup tables for WoW classes / specs.

Seeded from app/data/classes_specs.json on app start. The string slug is the
stable identifier we use everywhere (e.g. ``priest_holy``).
"""
from __future__ import annotations

import enum

from sqlalchemy import Enum as PgEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Role(str, enum.Enum):
    dps = "dps"
    healer = "healer"
    tank = "tank"


class GameClass(Base):
    __tablename__ = "game_classes"

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    name_en: Mapped[str] = mapped_column(String(48), nullable=False)
    name_de: Mapped[str] = mapped_column(String(48), nullable=False)
    color_hex: Mapped[str] = mapped_column(String(7), nullable=False)  # class color e.g. "#A330C9"

    specs: Mapped[list["GameSpec"]] = relationship(back_populates="game_class", lazy="selectin")


class GameSpec(Base):
    __tablename__ = "game_specs"

    slug: Mapped[str] = mapped_column(String(48), primary_key=True)  # e.g. "priest_holy"
    class_slug: Mapped[str] = mapped_column(
        ForeignKey("game_classes.slug", ondelete="CASCADE"), nullable=False, index=True
    )
    name_en: Mapped[str] = mapped_column(String(48), nullable=False)
    name_de: Mapped[str] = mapped_column(String(48), nullable=False)
    role: Mapped[Role] = mapped_column(PgEnum(Role, name="game_role"), nullable=False)
    wcl_spec_id: Mapped[int] = mapped_column(nullable=False)  # WCL specID

    game_class: Mapped[GameClass] = relationship(back_populates="specs", lazy="joined")
