"""Parse WCL URLs and the JSON payloads returned by our GraphQL queries.

WCL URL shapes we accept (all yield the same code):
- https://www.warcraftlogs.com/reports/{CODE}
- https://www.warcraftlogs.com/reports/{CODE}#fight=42
- https://classic.warcraftlogs.com/reports/{CODE}
- bare {CODE} (16-character alphanumeric WCL id)
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.core.errors import ValidationAppError

_WCL_CODE_RE = re.compile(r"^[A-Za-z0-9]{16}$")
_WCL_URL_RE = re.compile(r"warcraftlogs\.com/reports/([A-Za-z0-9]{16})")


def parse_report_input(value: str) -> str:
    """Return the bare WCL report code from a URL or pasted code."""
    value = (value or "").strip()
    if not value:
        raise ValidationAppError("No report URL or code provided.")
    if _WCL_CODE_RE.match(value):
        return value
    m = _WCL_URL_RE.search(value)
    if m:
        return m.group(1)
    raise ValidationAppError("Could not extract a Warcraft Logs report code from the input.")


def _ms_to_dt(ms: float | int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def parse_report_overview(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalise the ``reportData.report`` overview into a dict ready for ORM use."""
    rd = (payload or {}).get("reportData", {})
    report = rd.get("report") if rd else None
    if not report:
        raise ValidationAppError("Report not found on Warcraft Logs (private or invalid code?).")
    zone = report.get("zone") or {}
    region = report.get("region") or {}
    fights_in = report.get("fights") or []
    fights = []
    for f in fights_in:
        start_ms = report["startTime"] + f.get("startTime", 0)
        end_ms = report["startTime"] + f.get("endTime", f.get("startTime", 0))
        fights.append(
            {
                "fight_id": int(f["id"]),
                "encounter_id": int(f["encounterID"]) if f.get("encounterID") else None,
                "name": f.get("name") or "",
                "difficulty": f.get("difficulty"),
                "keystone_level": f.get("keystoneLevel"),
                "is_kill": bool(f.get("kill")),
                "boss_percentage": f.get("bossPercentage"),
                "duration_ms": max(0, int(end_ms - start_ms)),
                "start_time": _ms_to_dt(start_ms),
            }
        )
    return {
        "wcl_code": report["code"],
        "title": report.get("title") or "",
        "zone_id": zone.get("id"),
        "zone_name": zone.get("name") or "",
        "region": region.get("compactName") or "",
        "game_version": (report.get("gameVersion") or "retail").lower(),
        "start_time": _ms_to_dt(report["startTime"]),
        "end_time": _ms_to_dt(report["endTime"]),
        "fights": fights,
    }


_WCL_CLASS_TO_SLUG = {
    "deathknight": "death_knight",
    "demonhunter": "demon_hunter",
    "druid": "druid",
    "evoker": "evoker",
    "hunter": "hunter",
    "mage": "mage",
    "monk": "monk",
    "paladin": "paladin",
    "priest": "priest",
    "rogue": "rogue",
    "shaman": "shaman",
    "warlock": "warlock",
    "warrior": "warrior",
}

_WCL_SPEC_NAME_TO_SLUG = {
    # death knight
    ("death_knight", "Blood"): "death_knight_blood",
    ("death_knight", "Frost"): "death_knight_frost",
    ("death_knight", "Unholy"): "death_knight_unholy",
    # dh
    ("demon_hunter", "Havoc"): "demon_hunter_havoc",
    ("demon_hunter", "Vengeance"): "demon_hunter_vengeance",
    # druid
    ("druid", "Balance"): "druid_balance",
    ("druid", "Feral"): "druid_feral",
    ("druid", "Guardian"): "druid_guardian",
    ("druid", "Restoration"): "druid_restoration",
    # evoker
    ("evoker", "Devastation"): "evoker_devastation",
    ("evoker", "Preservation"): "evoker_preservation",
    ("evoker", "Augmentation"): "evoker_augmentation",
    # hunter
    ("hunter", "BeastMastery"): "hunter_beast_mastery",
    ("hunter", "Beast Mastery"): "hunter_beast_mastery",
    ("hunter", "Marksmanship"): "hunter_marksmanship",
    ("hunter", "Survival"): "hunter_survival",
    # mage
    ("mage", "Arcane"): "mage_arcane",
    ("mage", "Fire"): "mage_fire",
    ("mage", "Frost"): "mage_frost",
    # monk
    ("monk", "Brewmaster"): "monk_brewmaster",
    ("monk", "Mistweaver"): "monk_mistweaver",
    ("monk", "Windwalker"): "monk_windwalker",
    # paladin
    ("paladin", "Holy"): "paladin_holy",
    ("paladin", "Protection"): "paladin_protection",
    ("paladin", "Retribution"): "paladin_retribution",
    # priest
    ("priest", "Discipline"): "priest_discipline",
    ("priest", "Holy"): "priest_holy",
    ("priest", "Shadow"): "priest_shadow",
    # rogue
    ("rogue", "Assassination"): "rogue_assassination",
    ("rogue", "Outlaw"): "rogue_outlaw",
    ("rogue", "Subtlety"): "rogue_subtlety",
    # shaman
    ("shaman", "Elemental"): "shaman_elemental",
    ("shaman", "Enhancement"): "shaman_enhancement",
    ("shaman", "Restoration"): "shaman_restoration",
    # warlock
    ("warlock", "Affliction"): "warlock_affliction",
    ("warlock", "Demonology"): "warlock_demonology",
    ("warlock", "Destruction"): "warlock_destruction",
    # warrior
    ("warrior", "Arms"): "warrior_arms",
    ("warrior", "Fury"): "warrior_fury",
    ("warrior", "Protection"): "warrior_protection",
}


def class_slug_from_wcl(wcl_class: str | None) -> str:
    if not wcl_class:
        return ""
    key = wcl_class.replace(" ", "").lower()
    return _WCL_CLASS_TO_SLUG.get(key, "")


def spec_slug_from_wcl(class_slug: str, wcl_spec: str | None) -> str:
    if not wcl_spec:
        return ""
    key = (class_slug, wcl_spec.replace(" ", ""))
    if key in _WCL_SPEC_NAME_TO_SLUG:
        return _WCL_SPEC_NAME_TO_SLUG[key]
    key2 = (class_slug, wcl_spec)
    return _WCL_SPEC_NAME_TO_SLUG.get(key2, "")


def role_from_spec_slug(spec_slug: str, fallback: str = "dps") -> str:
    """Best-effort role inference; the real source of truth is the GameSpec table."""
    healers = {
        "druid_restoration",
        "evoker_preservation",
        "monk_mistweaver",
        "paladin_holy",
        "priest_discipline",
        "priest_holy",
        "shaman_restoration",
    }
    tanks = {
        "death_knight_blood",
        "demon_hunter_vengeance",
        "druid_guardian",
        "monk_brewmaster",
        "paladin_protection",
        "warrior_protection",
    }
    if spec_slug in healers:
        return "healer"
    if spec_slug in tanks:
        return "tank"
    return fallback


def parse_player_details(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten the ``playerDetails`` field into a list of role-tagged players.

    The shape of the GraphQL response is ``{data: {dps: [], healers: [], tanks: []}}``
    where each entry has at least ``name``, ``server``, ``id``, ``type`` (class),
    ``specs`` (list of {{spec, role, count}}), ``minItemLevel``, ``maxItemLevel``.
    """
    out: list[dict[str, Any]] = []
    rd = (payload or {}).get("reportData", {})
    report = rd.get("report") if rd else None
    if not report:
        return out
    raw = report.get("playerDetails") or {}
    inner = raw.get("data") or raw  # WCL nests under "data"
    for role_key, role_value in (("dps", "dps"), ("healers", "healer"), ("tanks", "tank")):
        for p in inner.get(role_key, []) or []:
            class_slug = class_slug_from_wcl(p.get("type"))
            specs = p.get("specs") or []
            best_spec = max(specs, key=lambda s: int(s.get("count", 0))) if specs else {}
            spec_slug = spec_slug_from_wcl(class_slug, best_spec.get("spec")) if class_slug else ""
            ilvl = p.get("maxItemLevel") or p.get("minItemLevel")
            out.append(
                {
                    "actor_id": int(p["id"]),
                    "name": p.get("name") or "",
                    "server": p.get("server") or "",
                    "class_slug": class_slug,
                    "spec_slug": spec_slug,
                    "role": role_value,
                    "item_level": float(ilvl) if ilvl is not None else None,
                    "talents_loadout": p.get("talentLoadout"),
                    "raw": p,
                }
            )
    return out


def parse_damage_done_table(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """Return ``{actor_id: {damage_done, dps}}`` from a DamageDone table response."""
    rd = (payload or {}).get("reportData", {})
    report = rd.get("report") if rd else None
    table = (report or {}).get("table") or {}
    inner = table.get("data") or table
    entries = inner.get("entries") or []
    total_time = float(inner.get("totalTime") or 0)
    out: dict[int, dict[str, Any]] = {}
    for e in entries:
        aid = int(e.get("id", 0))
        total = int(e.get("total", 0))
        active = float(e.get("activeTime", total_time))
        dps = (total / active * 1000) if active else 0.0
        out[aid] = {"damage_done": total, "dps": dps}
    return out


def parse_healing_done_table(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rd = (payload or {}).get("reportData", {})
    report = rd.get("report") if rd else None
    table = (report or {}).get("table") or {}
    inner = table.get("data") or table
    entries = inner.get("entries") or []
    total_time = float(inner.get("totalTime") or 0)
    out: dict[int, dict[str, Any]] = {}
    for e in entries:
        aid = int(e.get("id", 0))
        total = int(e.get("total", 0))
        active = float(e.get("activeTime", total_time))
        hps = (total / active * 1000) if active else 0.0
        out[aid] = {"healing_done": total, "hps": hps}
    return out


def parse_deaths_table(payload: dict[str, Any]) -> dict[int, int]:
    rd = (payload or {}).get("reportData", {})
    report = rd.get("report") if rd else None
    table = (report or {}).get("table") or {}
    inner = table.get("data") or table
    entries = inner.get("entries") or []
    counts: dict[int, int] = {}
    for e in entries:
        aid = int(e.get("id", 0))
        counts[aid] = counts.get(aid, 0) + 1
    return counts


def parse_casts_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rd = (payload or {}).get("reportData", {})
    report = rd.get("report") if rd else None
    table = (report or {}).get("table") or {}
    inner = table.get("data") or table
    entries = inner.get("entries") or []
    out: list[dict[str, Any]] = []
    for e in entries:
        gid = e.get("guid") or e.get("id")
        if gid is None:
            continue
        out.append(
            {
                "ability_id": int(gid),
                "ability_name": str(e.get("name") or ""),
                "casts": int(e.get("hitCount") or e.get("total") or 0),
                "hits": int(e.get("hitCount") or 0),
                "total": int(e.get("total") or 0),
                "icon": e.get("abilityIcon"),
            }
        )
    return out


def parse_gear_from_player_details(player_raw: dict[str, Any]) -> list[dict[str, Any]]:
    gear = []
    for slot, item in enumerate(player_raw.get("combatantInfo", {}).get("gear") or []):
        if not item:
            continue
        gear.append(
            {
                "slot": int(slot),
                "item_id": int(item.get("id", 0)),
                "item_level": int(item.get("itemLevel")) if item.get("itemLevel") else None,
                "item_quality": int(item.get("quality")) if item.get("quality") is not None else None,
                "name": str(item.get("name") or ""),
                "icon": item.get("icon"),
                "enchant_id": int(item.get("permanentEnchant")) if item.get("permanentEnchant") else None,
                "gem_ids": [int(g["id"]) for g in (item.get("gems") or []) if g.get("id")],
                "bonus_ids": [int(b) for b in (item.get("bonusIDs") or [])],
            }
        )
    return gear


def parse_encounter_rankings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten ``worldData.encounter.characterRankings`` into a list of dicts."""
    wd = (payload or {}).get("worldData", {})
    enc = wd.get("encounter") if wd else None
    if not enc:
        return []
    rankings = (enc.get("characterRankings") or {}).get("rankings", [])
    out: list[dict[str, Any]] = []
    encounter_name = enc.get("name") or ""
    encounter_id = int(enc.get("id"))
    for idx, r in enumerate(rankings, start=1):
        out.append(
            {
                "encounter_id": encounter_id,
                "encounter_name": encounter_name,
                "rank": idx,
                "amount": float(r.get("amount") or 0),
                "item_level": float(r["bracketData"]) if r.get("bracketData") else None,
                "duration_ms": int(r["duration"]) if r.get("duration") else None,
                "character_name": r.get("name") or "",
                "server": (r.get("server") or {}).get("name", ""),
                "region": ((r.get("server") or {}).get("region") or {}).get("slug", ""),
                "wcl_report_code": (r.get("report") or {}).get("code", ""),
                "wcl_fight_id": int((r.get("report") or {}).get("fightID") or 0),
                "raw": r,
            }
        )
    return out
