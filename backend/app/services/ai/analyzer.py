"""Compose the AI prompt from DB data and run an analysis."""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.errors import NotFoundError, UpstreamError
from app.models import (
    Analysis,
    AnalysisStatus,
    AppSetting,
    Report,
    ReportFight,
    ReportPlayer,
    TopLog,
)
from app.services.ai.anthropic_provider import AnthropicProvider
from app.services.ai.base import AiProvider, AiResponse
from app.services.ai.prompts import build_user_prompt, system_prompt_for

logger = logging.getLogger(__name__)


def _provider() -> AiProvider:
    if settings.ai_provider == "anthropic":
        return AnthropicProvider()
    raise UpstreamError(f"Unsupported AI provider: {settings.ai_provider}")


async def _resolve_model(session: AsyncSession) -> str:
    row = (
        await session.execute(select(AppSetting).where(AppSetting.key == "ai_model"))
    ).scalar_one_or_none()
    if row and row.value:
        return str((row.value or {}).get("value") or settings.ai_model)
    return settings.ai_model


async def _fetch_top_log_references(
    session: AsyncSession, *, spec_slug: str, encounter_id: int | None, role: str, limit: int = 5
) -> list[dict[str, Any]]:
    if not encounter_id or not spec_slug:
        return []
    metric = "hps" if role == "healer" else "dps"
    stmt = (
        select(TopLog)
        .where(
            TopLog.spec_slug == spec_slug,
            TopLog.encounter_id == encounter_id,
            TopLog.metric == metric,
        )
        .order_by(TopLog.rank.asc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "rank": r.rank,
            "amount": r.amount,
            "item_level": r.item_level,
            "duration_ms": r.duration_ms,
            "character_name": r.character_name,
            "server": r.server,
            "region": r.region,
            "wcl_report_code": r.wcl_report_code,
            "wcl_fight_id": r.wcl_fight_id,
            "extras": r.detail_payload or r.payload,
        }
        for r in rows
    ]


async def request_analysis(
    session: AsyncSession,
    *,
    report_id: uuid.UUID,
    fight_id: uuid.UUID,
    player_id: uuid.UUID,
    requested_by_id: uuid.UUID | None,
    locale: str,
    provider: AiProvider | None = None,
) -> Analysis:
    """Create + run an analysis synchronously and return it."""
    # Fetch the player + fight + casts + gear
    stmt = (
        select(ReportPlayer)
        .where(ReportPlayer.id == player_id)
        .options(selectinload(ReportPlayer.casts), selectinload(ReportPlayer.gear))
    )
    player = (await session.execute(stmt)).scalar_one_or_none()
    if not player:
        raise NotFoundError("Player not found.")
    fight = (
        await session.execute(select(ReportFight).where(ReportFight.id == fight_id))
    ).scalar_one_or_none()
    if not fight or fight.id != player.fight_id:
        raise NotFoundError("Fight does not match the supplied player.")
    report = (
        await session.execute(select(Report).where(Report.id == report_id))
    ).scalar_one_or_none()
    if not report or report.id != fight.report_id:
        raise NotFoundError("Report mismatch.")

    role_focus = "healer" if player.role == "healer" else ("tank" if player.role == "tank" else "dps")
    references = await _fetch_top_log_references(
        session, spec_slug=player.spec_slug, encounter_id=fight.encounter_id, role=role_focus
    )

    fight_summary = {
        "encounter_id": fight.encounter_id,
        "encounter_name": fight.name,
        "difficulty": fight.difficulty,
        "keystone_level": fight.keystone_level,
        "is_kill": fight.is_kill,
        "duration_ms": fight.duration_ms,
        "boss_percentage": fight.boss_percentage,
    }
    player_summary = {
        "name": player.name,
        "server": player.server,
        "class": player.class_slug,
        "spec": player.spec_slug,
        "role": player.role,
        "item_level": player.item_level,
        "dps": player.dps,
        "hps": player.hps,
        "damage_done": player.damage_done,
        "healing_done": player.healing_done,
        "deaths": player.deaths,
        "talents_loadout": player.talents_loadout,
    }
    casts = [
        {
            "ability_id": c.ability_id,
            "name": c.ability_name,
            "casts": c.casts,
            "hits": c.hits,
            "total": c.total,
        }
        for c in player.casts
    ]
    gear = [
        {
            "slot": g.slot,
            "item_id": g.item_id,
            "item_level": g.item_level,
            "name": g.name,
            "enchant_id": g.enchant_id,
            "gem_ids": g.gem_ids,
        }
        for g in player.gear
    ]

    chosen_model = await _resolve_model(session)
    analysis = Analysis(
        requested_by_id=requested_by_id,
        report_id=report.id,
        fight_id=fight.id,
        player_id=player.id,
        locale=locale,
        status=AnalysisStatus.running,
        provider=settings.ai_provider,
        model=chosen_model,
    )
    session.add(analysis)
    await session.flush()

    used_provider = provider or _provider()
    user_prompt = build_user_prompt(
        locale=locale if locale in ("en", "de") else "en",  # type: ignore[arg-type]
        role_focus=role_focus,  # type: ignore[arg-type]
        fight_summary=fight_summary,
        player_summary=player_summary,
        casts=casts,
        gear=gear,
        top_log_references=references,
    )
    sys_prompt = system_prompt_for("de" if locale == "de" else "en")

    try:
        response: AiResponse = await used_provider.generate_structured(
            system_prompt=sys_prompt, user_prompt=user_prompt, model=chosen_model
        )
        analysis.status = AnalysisStatus.succeeded
        analysis.summary = response.text
        analysis.structured = response.structured or {}
        analysis.prompt_tokens = response.prompt_tokens
        analysis.completion_tokens = response.completion_tokens
        analysis.model = response.model
    except Exception as exc:  # noqa: BLE001
        logger.exception("AI analysis failed")
        analysis.status = AnalysisStatus.failed
        analysis.error = str(exc)
    return analysis
