"""Import + cache localized WoW game data from wago.tools.

We pull three DBC tables, EN+DE locales each, and upsert into
``wow_localizations``:

- ``SpellName`` → kind=``spell`` (covers spells, talents and boss abilities)
- ``ItemSparse`` → kind=``item`` (also captures quality + inventory slot in extras)
- ``JournalEncounter`` → kind=``encounter`` (matches WCL's ``encounter_id``)

Each row's primary key is ``(kind, game_id, locale)``, so re-importing simply
upserts. The whole import runs in a single ``WowDataImport`` row that flips to
``success`` on the final commit.
"""
from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Iterable

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UpstreamError
from app.models import WowDataImport, WowImportStatus, WowLocalization

logger = logging.getLogger(__name__)

WAGO_BASE = "https://wago.tools"
LOCALES: tuple[tuple[str, str], ...] = (("en", "enUS"), ("de", "deDE"))

# Larger CSVs (ItemSparse weighs ~80 MB / locale) require a generous timeout
# and a bigger HTTP read buffer; httpx defaults are fine for now.
_HTTP_TIMEOUT = httpx.Timeout(connect=15, read=600, write=60, pool=15)


# --------------------------------------------------------------------------------------
# Build / manifest
# --------------------------------------------------------------------------------------


async def fetch_latest_build(client: httpx.AsyncClient | None = None) -> str:
    """Return the version string of the latest *live* retail build."""
    own = client is None
    http = client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    try:
        resp = await http.get(f"{WAGO_BASE}/api/builds")
        resp.raise_for_status()
        payload = resp.json()
    except httpx.HTTPError as exc:
        raise UpstreamError(f"wago.tools manifest unreachable: {exc}") from exc
    finally:
        if own:
            await http.aclose()

    builds = payload.get("wow") or []
    if not builds:
        raise UpstreamError("wago.tools manifest had no 'wow' entries.")
    # The first entry is the most recent. Skip background-download (BGDL)
    # placeholders that don't have full data published yet.
    for entry in builds:
        if entry.get("is_bgdl"):
            continue
        version = entry.get("version")
        if version:
            return str(version)
    return str(builds[0].get("version") or "")


# --------------------------------------------------------------------------------------
# CSV download + parse
# --------------------------------------------------------------------------------------


async def _download_csv(client: httpx.AsyncClient, table: str, build: str, locale_code: str) -> str:
    url = f"{WAGO_BASE}/db2/{table}/csv"
    try:
        resp = await client.get(url, params={"build": build, "locale": locale_code})
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise UpstreamError(f"wago.tools CSV {table} ({locale_code}) failed: {exc}") from exc
    if "text/csv" not in (resp.headers.get("content-type") or ""):
        raise UpstreamError(f"wago.tools returned non-CSV for {table}: {resp.text[:200]}")
    return resp.text


def _iter_rows(csv_text: str) -> Iterable[dict[str, str]]:
    return csv.DictReader(io.StringIO(csv_text))


# --------------------------------------------------------------------------------------
# Upsert helpers
# --------------------------------------------------------------------------------------


_BATCH = 5000


async def _upsert_localizations(
    session: AsyncSession, rows: list[dict[str, Any]]
) -> int:
    """Insert/update localization rows in chunks; returns count of input rows."""
    if not rows:
        return 0
    total = 0
    for start in range(0, len(rows), _BATCH):
        chunk = rows[start : start + _BATCH]
        stmt = pg_insert(WowLocalization).values(chunk)
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                WowLocalization.kind,
                WowLocalization.game_id,
                WowLocalization.locale,
            ],
            set_={"name": stmt.excluded.name, "extras": stmt.excluded.extras},
        )
        await session.execute(stmt)
        total += len(chunk)
        # Commit between chunks so a crash doesn't lose hours of work and
        # admins can see partial progress in the UI.
        await session.commit()
    return total


# --------------------------------------------------------------------------------------
# Per-table importers
# --------------------------------------------------------------------------------------


async def _import_spell_names(
    session: AsyncSession, client: httpx.AsyncClient, build: str
) -> int:
    total = 0
    for locale_short, locale_code in LOCALES:
        text = await _download_csv(client, "SpellName", build, locale_code)
        rows: list[dict[str, Any]] = []
        for entry in _iter_rows(text):
            try:
                game_id = int(entry["ID"])
            except (KeyError, ValueError):
                continue
            name = (entry.get("Name_lang") or "").strip()
            if not name:
                continue
            rows.append(
                {
                    "kind": "spell",
                    "game_id": game_id,
                    "locale": locale_short,
                    "name": name,
                    "extras": {},
                }
            )
        n = await _upsert_localizations(session, rows)
        logger.info("imported SpellName/%s: %s rows", locale_code, n)
        total += n
    return total


async def _import_items(
    session: AsyncSession, client: httpx.AsyncClient, build: str
) -> int:
    total = 0
    for locale_short, locale_code in LOCALES:
        text = await _download_csv(client, "ItemSparse", build, locale_code)
        rows: list[dict[str, Any]] = []
        for entry in _iter_rows(text):
            try:
                game_id = int(entry["ID"])
            except (KeyError, ValueError):
                continue
            name = (entry.get("Display_lang") or "").strip()
            if not name:
                continue
            extras: dict[str, Any] = {}
            quality = entry.get("OverallQualityID")
            if quality:
                try:
                    extras["quality"] = int(quality)
                except ValueError:
                    pass
            inv_type = entry.get("InventoryType")
            if inv_type:
                try:
                    extras["inventory_type"] = int(inv_type)
                except ValueError:
                    pass
            rows.append(
                {
                    "kind": "item",
                    "game_id": game_id,
                    "locale": locale_short,
                    "name": name,
                    "extras": extras,
                }
            )
        n = await _upsert_localizations(session, rows)
        logger.info("imported ItemSparse/%s: %s rows", locale_code, n)
        total += n
    return total


async def _import_encounters(
    session: AsyncSession, client: httpx.AsyncClient, build: str
) -> int:
    total = 0
    for locale_short, locale_code in LOCALES:
        text = await _download_csv(client, "JournalEncounter", build, locale_code)
        rows: list[dict[str, Any]] = []
        for entry in _iter_rows(text):
            try:
                game_id = int(entry["ID"])
            except (KeyError, ValueError):
                continue
            name = (entry.get("Name_lang") or "").strip()
            if not name:
                continue
            extras: dict[str, Any] = {}
            dungeon_enc = entry.get("DungeonEncounterID")
            if dungeon_enc:
                try:
                    extras["dungeon_encounter_id"] = int(dungeon_enc)
                except ValueError:
                    pass
            instance = entry.get("JournalInstanceID")
            if instance:
                try:
                    extras["journal_instance_id"] = int(instance)
                except ValueError:
                    pass
            rows.append(
                {
                    "kind": "encounter",
                    "game_id": game_id,
                    "locale": locale_short,
                    "name": name,
                    "extras": extras,
                }
            )
        n = await _upsert_localizations(session, rows)
        logger.info("imported JournalEncounter/%s: %s rows", locale_code, n)
        total += n
    return total


# --------------------------------------------------------------------------------------
# Orchestrator
# --------------------------------------------------------------------------------------


async def run_full_import(session: AsyncSession, *, build: str | None = None) -> WowDataImport:
    """Pull SpellName + ItemSparse + JournalEncounter for EN+DE.

    Creates a ``WowDataImport`` row tagged ``in_progress`` immediately, then
    flips it to ``success`` (or ``failed``) at the end with the row count.
    Concurrent runs are prevented by checking for an existing ``in_progress``
    row of the same build.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        if not build:
            build = await fetch_latest_build(client)

        # Sweep stale in_progress rows from a previous run that got killed
        # before it could flip status (container restart, etc.). 30 min is
        # comfortably longer than a successful import takes (~3-5 min).
        from datetime import timedelta as _td

        stale_cutoff = datetime.now(UTC) - _td(minutes=30)
        await session.execute(
            WowDataImport.__table__.update()
            .where(
                WowDataImport.status == WowImportStatus.in_progress.value,
                WowDataImport.started_at < stale_cutoff,
            )
            .values(
                status=WowImportStatus.failed.value,
                finished_at=datetime.now(UTC),
                notes="abandoned (no progress for >30 min)",
            )
        )
        await session.commit()

        existing = (
            await session.execute(
                select(WowDataImport)
                .where(
                    WowDataImport.build == build,
                    WowDataImport.status == WowImportStatus.in_progress.value,
                )
                .order_by(WowDataImport.started_at.desc())
            )
        ).scalar_one_or_none()
        if existing:
            logger.info("WoW data import for build %s is already in progress", build)
            return existing

        run = WowDataImport(
            id=uuid.uuid4(),
            build=build,
            status=WowImportStatus.in_progress.value,
            started_at=datetime.now(UTC),
            rows_imported=0,
            source="wago.tools",
        )
        session.add(run)
        await session.commit()

        try:
            spells = await _import_spell_names(session, client, build)
            items = await _import_items(session, client, build)
            encounters = await _import_encounters(session, client, build)
            run.rows_imported = spells + items + encounters
            run.status = WowImportStatus.success.value
            run.finished_at = datetime.now(UTC)
            run.notes = (
                f"spells={spells} items={items} encounters={encounters}"
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("WoW data import failed for build %s", build)
            run.status = WowImportStatus.failed.value
            run.finished_at = datetime.now(UTC)
            run.notes = str(exc)[:1000]
            await session.commit()
            raise

        await session.commit()
        return run


# --------------------------------------------------------------------------------------
# Read APIs (used by analyzer + admin endpoints)
# --------------------------------------------------------------------------------------


async def latest_import(session: AsyncSession) -> WowDataImport | None:
    return (
        await session.execute(
            select(WowDataImport).order_by(WowDataImport.started_at.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def list_imports(session: AsyncSession, limit: int = 20) -> list[WowDataImport]:
    return list(
        (
            await session.execute(
                select(WowDataImport)
                .order_by(WowDataImport.started_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )


async def lookup_names(
    session: AsyncSession,
    *,
    locale: str,
    spell_ids: Iterable[int] = (),
    item_ids: Iterable[int] = (),
    encounter_ids: Iterable[int] = (),
) -> dict[str, str]:
    """Return ``{"spell:123": "Name", "item:42": "...", ...}`` for the given IDs.

    Always falls back to English when a translation is missing (e.g. brand-new
    spells that haven't been translated yet, or imports that haven't finished).
    """
    if locale not in {"en", "de"}:
        locale = "en"
    spell_ids = list({int(x) for x in spell_ids if x})
    item_ids = list({int(x) for x in item_ids if x})
    encounter_ids = list({int(x) for x in encounter_ids if x})

    if not (spell_ids or item_ids or encounter_ids):
        return {}

    out: dict[str, str] = {}

    async def _fill(target_locale: str, missing_only: bool) -> None:
        clauses: list = []
        if spell_ids:
            clauses.append(
                (WowLocalization.kind == "spell")
                & (WowLocalization.game_id.in_(spell_ids))
            )
        if item_ids:
            clauses.append(
                (WowLocalization.kind == "item")
                & (WowLocalization.game_id.in_(item_ids))
            )
        if encounter_ids:
            clauses.append(
                (WowLocalization.kind == "encounter")
                & (WowLocalization.game_id.in_(encounter_ids))
            )
        if not clauses:
            return
        from sqlalchemy import or_

        stmt = (
            select(WowLocalization.kind, WowLocalization.game_id, WowLocalization.name)
            .where(WowLocalization.locale == target_locale)
            .where(or_(*clauses))
        )
        for kind, game_id, name in (await session.execute(stmt)).all():
            key = f"{kind}:{game_id}"
            if missing_only and key in out:
                continue
            out[key] = name

    await _fill(locale, missing_only=False)
    if locale != "en":
        # Fall back to English for anything we didn't get a localised hit for.
        await _fill("en", missing_only=True)
    return out


async def resolve_encounter_names_with_fallback(
    session: AsyncSession,
    *,
    locale: str,
    encounters: list[tuple[int, str]],
) -> dict[int, str]:
    """Resolve WCL ``(encounter_id, english_name)`` pairs to localised names.

    WCL's encounter IDs and Blizzard's ``JournalEncounter.ID`` only line up
    sometimes (WCL invents its own IDs for new tiers), so we try the direct
    ID lookup first and fall back to a name match against the English DBC
    table for anything that didn't resolve.
    """
    if locale not in {"en", "de"}:
        locale = "en"

    out: dict[int, str] = {}
    if not encounters:
        return out

    direct = await lookup_names(
        session,
        locale=locale,
        encounter_ids=[eid for eid, _ in encounters],
    )
    for eid, _ in encounters:
        key = f"encounter:{eid}"
        if key in direct:
            out[eid] = direct[key]

    missing = [
        (eid, name) for (eid, name) in encounters if eid not in out and name
    ]
    if missing:
        names_en = list({n for _, n in missing})
        en_rows = (
            await session.execute(
                select(WowLocalization.name, WowLocalization.game_id)
                .where(
                    WowLocalization.kind == "encounter",
                    WowLocalization.locale == "en",
                    WowLocalization.name.in_(names_en),
                )
            )
        ).all()
        en_to_dbc = {name: gid for name, gid in en_rows}
        dbc_ids = list(set(en_to_dbc.values()))
        if dbc_ids:
            target_rows = (
                await session.execute(
                    select(WowLocalization.game_id, WowLocalization.name)
                    .where(
                        WowLocalization.kind == "encounter",
                        WowLocalization.locale == locale,
                        WowLocalization.game_id.in_(dbc_ids),
                    )
                )
            ).all()
            dbc_to_name = {gid: name for gid, name in target_rows}
            for eid, en_name in missing:
                dbc_id = en_to_dbc.get(en_name)
                if dbc_id and dbc_id in dbc_to_name:
                    out[eid] = dbc_to_name[dbc_id]
    return out


async def localization_stats(session: AsyncSession) -> dict[str, dict[str, int]]:
    """Counts per (kind, locale) — handy for the admin status card."""
    stmt = select(
        WowLocalization.kind,
        WowLocalization.locale,
        func.count().label("n"),
    ).group_by(WowLocalization.kind, WowLocalization.locale)
    out: dict[str, dict[str, int]] = {}
    for kind, locale, count in (await session.execute(stmt)).all():
        out.setdefault(kind, {})[locale] = int(count)
    return out
