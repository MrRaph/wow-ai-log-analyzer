"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-08 00:00:00
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    user_role = postgresql.ENUM("user", "admin", name="user_role", create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM("user", "admin", name="user_role", create_type=False), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locale", sa.String(8), nullable=False, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("invited_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_invites_email", "invites", ["email"])

    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    role_enum = postgresql.ENUM("dps", "healer", "tank", name="game_role", create_type=False)
    role_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "game_classes",
        sa.Column("slug", sa.String(32), primary_key=True),
        sa.Column("name_en", sa.String(48), nullable=False),
        sa.Column("name_de", sa.String(48), nullable=False),
        sa.Column("color_hex", sa.String(7), nullable=False),
    )

    op.create_table(
        "game_specs",
        sa.Column("slug", sa.String(48), primary_key=True),
        sa.Column("class_slug", sa.String(32), sa.ForeignKey("game_classes.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("name_en", sa.String(48), nullable=False),
        sa.Column("name_de", sa.String(48), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column("wcl_spec_id", sa.Integer, nullable=False),
    )
    op.create_index("ix_game_specs_class_slug", "game_specs", ["class_slug"])

    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("wcl_code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False, server_default=""),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("zone_id", sa.Integer, nullable=True),
        sa.Column("zone_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("region", sa.String(8), nullable=False, server_default=""),
        sa.Column("game_version", sa.String(16), nullable=False, server_default="retail"),
        sa.Column("raw_meta", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("wcl_code", name="uq_reports_wcl_code"),
    )
    op.create_index("ix_reports_wcl_code", "reports", ["wcl_code"])
    op.create_index("ix_reports_owner_user_id", "reports", ["owner_user_id"])

    op.create_table(
        "report_fights",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fight_id", sa.Integer, nullable=False),
        sa.Column("encounter_id", sa.Integer, nullable=True),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("difficulty", sa.Integer, nullable=True),
        sa.Column("keystone_level", sa.Integer, nullable=True),
        sa.Column("is_kill", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("boss_percentage", sa.Float, nullable=True),
        sa.Column("duration_ms", sa.BigInteger, nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_id", "fight_id", name="uq_report_fights_report_fight"),
    )
    op.create_index("ix_report_fights_report_id", "report_fights", ["report_id"])
    op.create_index("ix_report_fights_encounter_id", "report_fights", ["encounter_id"])

    op.create_table(
        "report_players",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fight_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_fights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("server", sa.String(64), nullable=False, server_default=""),
        sa.Column("class_slug", sa.String(32), nullable=False),
        sa.Column("spec_slug", sa.String(48), nullable=False),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("item_level", sa.Float, nullable=True),
        sa.Column("dps", sa.Float, nullable=True),
        sa.Column("hps", sa.Float, nullable=True),
        sa.Column("damage_done", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("healing_done", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("deaths", sa.Integer, nullable=False, server_default="0"),
        sa.Column("talents_loadout", sa.String(2048), nullable=True),
        sa.Column("extras", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_report_players_fight_id", "report_players", ["fight_id"])
    op.create_index("ix_report_players_class_slug", "report_players", ["class_slug"])
    op.create_index("ix_report_players_spec", "report_players", ["spec_slug"])

    op.create_table(
        "report_player_casts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ability_id", sa.Integer, nullable=False),
        sa.Column("ability_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("casts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hits", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("icon", sa.String(255), nullable=True),
        sa.UniqueConstraint("player_id", "ability_id", name="uq_report_player_casts_player_ability"),
    )
    op.create_index("ix_report_player_casts_player_id", "report_player_casts", ["player_id"])
    op.create_index("ix_report_player_casts_ability", "report_player_casts", ["ability_id"])

    op.create_table(
        "report_player_gear",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot", sa.Integer, nullable=False),
        sa.Column("item_id", sa.Integer, nullable=False),
        sa.Column("item_level", sa.Integer, nullable=True),
        sa.Column("item_quality", sa.Integer, nullable=True),
        sa.Column("name", sa.String(128), nullable=False, server_default=""),
        sa.Column("icon", sa.String(255), nullable=True),
        sa.Column("enchant_id", sa.Integer, nullable=True),
        sa.Column("gem_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("bonus_ids", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.UniqueConstraint("player_id", "slot", name="uq_report_player_gear_player_slot"),
    )
    op.create_index("ix_report_player_gear_player_id", "report_player_gear", ["player_id"])

    op.create_table(
        "top_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("spec_slug", sa.String(48), sa.ForeignKey("game_specs.slug", ondelete="CASCADE"), nullable=False),
        sa.Column("encounter_id", sa.Integer, nullable=False),
        sa.Column("encounter_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("difficulty", sa.Integer, nullable=True),
        sa.Column("metric", sa.String(8), nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("item_level", sa.Float, nullable=True),
        sa.Column("duration_ms", sa.BigInteger, nullable=True),
        sa.Column("character_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("server", sa.String(64), nullable=False, server_default=""),
        sa.Column("region", sa.String(8), nullable=False, server_default=""),
        sa.Column("wcl_report_code", sa.String(32), nullable=False),
        sa.Column("wcl_fight_id", sa.Integer, nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("detail_payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_top_logs_spec_slug", "top_logs", ["spec_slug"])
    op.create_index("ix_top_logs_encounter_id", "top_logs", ["encounter_id"])
    op.create_index("ix_top_logs_lookup", "top_logs", ["spec_slug", "encounter_id", "rank"])

    analysis_status = postgresql.ENUM(
        "pending", "running", "succeeded", "failed", name="analysis_status", create_type=False
    )
    analysis_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("reports.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fight_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_fights.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("report_players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("locale", sa.String(8), nullable=False, server_default="en"),
        sa.Column("status", analysis_status, nullable=False, server_default="pending"),
        sa.Column("provider", sa.String(32), nullable=False, server_default="anthropic"),
        sa.Column("model", sa.String(64), nullable=False, server_default=""),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("structured", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_analyses_requested_by_id", "analyses", ["requested_by_id"])
    op.create_index("ix_analyses_report_id", "analyses", ["report_id"])
    op.create_index("ix_analyses_fight_id", "analyses", ["fight_id"])
    op.create_index("ix_analyses_player_id", "analyses", ["player_id"])
    op.create_index("ix_analyses_status", "analyses", ["status"])


def downgrade() -> None:
    op.drop_table("analyses")
    op.execute("DROP TYPE IF EXISTS analysis_status")
    op.drop_table("top_logs")
    op.drop_table("report_player_gear")
    op.drop_table("report_player_casts")
    op.drop_table("report_players")
    op.drop_table("report_fights")
    op.drop_table("reports")
    op.drop_table("game_specs")
    op.drop_table("game_classes")
    op.execute("DROP TYPE IF EXISTS game_role")
    op.drop_table("app_settings")
    op.drop_table("invites")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")
