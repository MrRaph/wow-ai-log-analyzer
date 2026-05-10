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
    """Download a single CSV with bounded retries.

    wago.tools returns 502/503/504 fairly often for large tables on fresh
    builds (the file is regenerated lazily on first request and the
    upstream proxy times out before the worker finishes). Retrying after
    a short wait almost always succeeds — by the time we come back, the
    file is cached. We retry on any HTTPError (timeout, connection reset,
    5xx) up to 4 times with exponential backoff capped at 30 s.
    """
    import asyncio

    url = f"{WAGO_BASE}/db2/{table}/csv"
    max_attempts = 4
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = await client.get(url, params={"build": build, "locale": locale_code})
            resp.raise_for_status()
            if "text/csv" not in (resp.headers.get("content-type") or ""):
                raise UpstreamError(
                    f"wago.tools returned non-CSV for {table}: {resp.text[:200]}"
                )
            return resp.text
        except httpx.HTTPError as exc:
            last_exc = exc
            # Don't retry on 4xx — that's a client bug (wrong build/table).
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500:
                break
            if attempt == max_attempts:
                break
            backoff = min(30, 2 ** attempt)  # 2s, 4s, 8s, 16s, 32→30
            logger.warning(
                "wago.tools CSV %s (%s) attempt %d failed: %s — retrying in %ds",
                table,
                locale_code,
                attempt,
                exc,
                backoff,
            )
            await asyncio.sleep(backoff)
    raise UpstreamError(
        f"wago.tools CSV {table} ({locale_code}) failed after {max_attempts} attempts: {last_exc}"
    ) from last_exc


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
    session: AsyncSession, client: httpx.AsyncClient, build: str, missing: list[str]
) -> int:
    """Import SpellName for every locale we know.

    A per-locale download failure (typical: deDE 504 because Blizzard
    publishes localized strings hours after enUS for fresh builds) does
    NOT abort the whole run — we log the locale, append it to ``missing``
    so the orchestrator can put it in the import notes, and move on. EN
    rows are usually enough; locales fill in on the next refresh.
    """
    total = 0
    for locale_short, locale_code in LOCALES:
        try:
            text = await _download_csv(client, "SpellName", build, locale_code)
        except UpstreamError as exc:
            logger.warning("SpellName/%s skipped: %s", locale_code, exc)
            missing.append(f"SpellName/{locale_code}")
            continue
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
    session: AsyncSession, client: httpx.AsyncClient, build: str, missing: list[str]
) -> int:
    total = 0
    for locale_short, locale_code in LOCALES:
        try:
            text = await _download_csv(client, "ItemSparse", build, locale_code)
        except UpstreamError as exc:
            logger.warning("ItemSparse/%s skipped: %s", locale_code, exc)
            missing.append(f"ItemSparse/{locale_code}")
            continue
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


async def _import_talents(
    session: AsyncSession, client: httpx.AsyncClient, build: str, missing: list[str]
) -> int:
    """Import the Trait* DBC chain so talent IDs from ``combatantInfo.talentTree``
    resolve to human-readable names.

    Why this is its own kind: the IDs WCL ships in ``talentTree`` are
    ``TraitNodeEntry.ID`` values, NOT ``Spell.ID`` values. They share an
    ID namespace with old MoP-era spells purely by accident, so looking
    them up under ``kind=spell`` returns confidently-wrong names ("Egg
    Shell" instead of "Festermight" etc.). We materialise a separate
    ``kind=talent`` row per (entry_id, locale) where the name is resolved
    via the chain:

        TraitNodeEntry.ID
          → TraitDefinition (via TraitDefinitionID)
              → OverrideName_lang  (explicit per-talent name, if any)
              → VisibleSpellID     (what the in-game UI shows)
              → SpellID            (canonical fallback)

    Both ``VisibleSpellID`` and ``SpellID`` are resolved against rows we
    already imported under ``kind=spell``, which is why this phase MUST
    run after ``_import_spell_names``.
    """
    # 1) Structural map: entry_id → trait_def_id (locale-agnostic).
    try:
        nodes_csv = await _download_csv(client, "TraitNodeEntry", build, "enUS")
    except UpstreamError as exc:
        logger.warning("TraitNodeEntry skipped: %s", exc)
        missing.append("TraitNodeEntry")
        return 0
    entry_to_def: dict[int, int] = {}
    for entry in _iter_rows(nodes_csv):
        try:
            eid = int(entry["ID"])
            did = int(entry["TraitDefinitionID"])
        except (KeyError, ValueError):
            continue
        if did:
            entry_to_def[eid] = did

    if not entry_to_def:
        missing.append("TraitNodeEntry/empty")
        return 0

    # 2) Per locale: download TraitDefinition (for OverrideName_lang) and
    # build entry → name. Spell-name fallback uses wow_localizations rows
    # we already imported under kind=spell.
    total = 0
    for locale_short, locale_code in LOCALES:
        try:
            defs_csv = await _download_csv(client, "TraitDefinition", build, locale_code)
        except UpstreamError as exc:
            logger.warning("TraitDefinition/%s skipped: %s", locale_code, exc)
            missing.append(f"TraitDefinition/{locale_code}")
            continue

        # def_id → (override_name, visible_spell_id, spell_id)
        defs: dict[int, tuple[str, int, int]] = {}
        for entry in _iter_rows(defs_csv):
            try:
                did = int(entry["ID"])
            except (KeyError, ValueError):
                continue
            override = (entry.get("OverrideName_lang") or "").strip()
            try:
                vsid = int(entry.get("VisibleSpellID") or 0)
            except ValueError:
                vsid = 0
            try:
                sid = int(entry.get("SpellID") or 0)
            except ValueError:
                sid = 0
            defs[did] = (override, vsid, sid)

        # Bulk-load every spell name we might need from the cache. We
        # gather the union of VisibleSpellID + SpellID across all
        # definitions, then a single SELECT pulls them.
        wanted_spell_ids: set[int] = set()
        for _, vsid, sid in defs.values():
            if vsid:
                wanted_spell_ids.add(vsid)
            if sid:
                wanted_spell_ids.add(sid)

        spell_names: dict[int, str] = {}
        if wanted_spell_ids:
            stmt = (
                select(WowLocalization.game_id, WowLocalization.name)
                .where(WowLocalization.kind == "spell")
                .where(WowLocalization.locale == locale_short)
                .where(WowLocalization.game_id.in_(wanted_spell_ids))
            )
            for gid, name in (await session.execute(stmt)).all():
                spell_names[int(gid)] = name

        rows: list[dict[str, Any]] = []
        skipped_no_name = 0
        for eid, did in entry_to_def.items():
            triple = defs.get(did)
            if triple is None:
                continue
            override, vsid, sid = triple
            name = override
            if not name and vsid:
                name = spell_names.get(vsid, "")
            if not name and sid:
                name = spell_names.get(sid, "")
            if not name:
                skipped_no_name += 1
                continue
            rows.append(
                {
                    "kind": "talent",
                    "game_id": eid,
                    "locale": locale_short,
                    "name": name,
                    "extras": {
                        "trait_definition_id": did,
                        "spell_id": sid or vsid or None,
                    },
                }
            )
        n = await _upsert_localizations(session, rows)
        logger.info(
            "imported Talent/%s: %s rows (skipped %s without resolvable name)",
            locale_code,
            n,
            skipped_no_name,
        )
        total += n
    return total


async def _import_encounters(
    session: AsyncSession, client: httpx.AsyncClient, build: str, missing: list[str]
) -> int:
    total = 0
    for locale_short, locale_code in LOCALES:
        try:
            text = await _download_csv(client, "JournalEncounter", build, locale_code)
        except UpstreamError as exc:
            logger.warning("JournalEncounter/%s skipped: %s", locale_code, exc)
            missing.append(f"JournalEncounter/{locale_code}")
            continue
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

        # Two cases for an "already in progress" row:
        #   1) Same build is already running → return it (idempotent).
        #   2) A "(pending)" placeholder row was just inserted by the API
        #      endpoint so the frontend's status chip flips to in_progress
        #      immediately. Adopt that row here, fill in the real build,
        #      and continue — no second row needed.
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

        pending = (
            await session.execute(
                select(WowDataImport)
                .where(
                    WowDataImport.build == "(pending)",
                    WowDataImport.status == WowImportStatus.in_progress.value,
                )
                .order_by(WowDataImport.started_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if pending is not None:
            run = pending
            run.build = build
            run.phase = "starting"
            await session.commit()
        else:
            run = WowDataImport(
                id=uuid.uuid4(),
                build=build,
                status=WowImportStatus.in_progress.value,
                started_at=datetime.now(UTC),
                rows_imported=0,
                source="wago.tools",
                phase="starting",
            )
            session.add(run)
            await session.commit()

        async def _set_phase(phase: str) -> None:
            run.phase = phase
            await session.commit()

        # Per-locale failures are appended here. If at least the EN side
        # of every kind made it through, we still flip the run to success
        # — the German strings will fill in on the next refresh once
        # Blizzard publishes them for this build.
        missing: list[str] = []
        try:
            await _set_phase("spells")
            spells = await _import_spell_names(session, client, build, missing)
            # Talents resolve via the spell cache so they MUST run after
            # _import_spell_names.
            await _set_phase("talents")
            talents = await _import_talents(session, client, build, missing)
            await _set_phase("items")
            items = await _import_items(session, client, build, missing)
            await _set_phase("encounters")
            encounters = await _import_encounters(session, client, build, missing)
            run.rows_imported = spells + talents + items + encounters
            run.finished_at = datetime.now(UTC)
            run.phase = ""

            # Decide whether we have enough to call this a success: at least
            # one locale must have landed for each table. Otherwise wago.tools
            # was completely unreachable and we mark the run failed so the
            # admin UI doesn't claim "Aktuell" for a half-empty cache.
            # Talents are best-effort — we don't fail the whole import if the
            # Trait* tables are missing for a fresh build.
            if spells == 0 or items == 0 or encounters == 0:
                run.status = WowImportStatus.failed.value
                run.notes = (
                    f"no rows imported (missing: {', '.join(missing) or 'all'})"
                )[:1000]
            else:
                run.status = WowImportStatus.success.value
                base = f"spells={spells} talents={talents} items={items} encounters={encounters}"
                if missing:
                    base += (
                        f" — partial (missing locales: {', '.join(missing)}); "
                        f"will retry on next refresh."
                    )
                run.notes = base[:1000]
        except Exception as exc:  # noqa: BLE001
            logger.exception("WoW data import failed for build %s", build)
            run.status = WowImportStatus.failed.value
            run.finished_at = datetime.now(UTC)
            run.phase = ""
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
    talent_ids: Iterable[int] = (),
) -> dict[str, str]:
    """Return ``{"spell:123": "Name", "item:42": "...", ...}`` for the given IDs.

    Always falls back to English when a translation is missing (e.g. brand-new
    spells that haven't been translated yet, or imports that haven't finished).

    ``talent_ids`` are resolved against ``kind=talent`` rows, which are the
    pre-resolved ``TraitNodeEntry → SpellName`` chain. Importantly we do NOT
    fall back to ``kind=spell`` for talents — the IDs collide with old spell
    IDs and would return confidently-wrong names ("Egg Shell" instead of
    "Festermight"). If the talent cache is missing or has no row for a given
    ID, we'd rather emit no name at all and let the AI know it can't cite it.
    """
    if locale not in {"en", "de"}:
        locale = "en"
    spell_ids = list({int(x) for x in spell_ids if x})
    item_ids = list({int(x) for x in item_ids if x})
    encounter_ids = list({int(x) for x in encounter_ids if x})
    talent_ids = list({int(x) for x in talent_ids if x})

    if not (spell_ids or item_ids or encounter_ids or talent_ids):
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
        if talent_ids:
            clauses.append(
                (WowLocalization.kind == "talent")
                & (WowLocalization.game_id.in_(talent_ids))
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
