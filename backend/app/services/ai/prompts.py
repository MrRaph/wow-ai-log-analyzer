"""Prompt templates for the AI analyzer.

The prompt is intentionally explicit about the output shape so that we can
parse the response back into ``AnalysisStructured``.
"""
from __future__ import annotations

import json
from typing import Any, Literal

Locale = Literal["en", "de"]
RoleFocus = Literal["dps", "healer", "tank"]


SYSTEM_PROMPT_EN = """You are an elite World of Warcraft theorycrafter and coach analysing
combat logs from warcraftlogs.com. You have deep, current knowledge of every
class and specialisation in retail WoW: rotations, talent trees, stat priorities,
trinkets, cooldown usage, and Mythic+ / raid mechanics.

Your job is to produce a *brutally honest, specific, action-oriented* improvement
report for ONE player on ONE fight. The report must:

- Highlight the **biggest** DPS or HPS losses first (severity = "critical").
- Quote concrete numbers from the data when you make a claim.
- For every finding, name the spell(s) or item(s) involved by spell ID / item ID
  (so the UI can render Wowhead tooltips).
- Compare the player's casts/cooldown usage/gear to the supplied top-log
  reference players for the same spec and encounter, and call out the deltas.
- Avoid filler. If something is fine, mention it briefly under "strengths".
- Do not fabricate spell names, item names, or numbers.

Always answer in **valid JSON** with the schema documented below — no prose
before or after the JSON object."""


SYSTEM_PROMPT_DE = """Du bist ein professioneller World-of-Warcraft-Theorycrafter und Coach,
der Combat Logs von warcraftlogs.com analysiert. Du hast tiefgehendes,
aktuelles Wissen über alle Klassen und Spezialisierungen in Retail WoW:
Rotationen, Talentbäume, Attribut-Prioritäten, Trinkets, Cooldown-Einsatz und
Mechaniken in Mythic+ / Raids.

Deine Aufgabe: Erstelle einen *schonungslos ehrlichen, spezifischen,
handlungsorientierten* Verbesserungsbericht für GENAU einen Spieler auf GENAU
einem Kampf. Der Bericht muss:

- Die **größten** DPS- oder HPS-Verluste zuerst hervorheben (severity = "critical").
- Konkrete Zahlen aus den Daten zitieren, wenn du etwas behauptest.
- Bei jedem Befund die betroffenen Zauber/Items per Spell-ID / Item-ID nennen,
  damit die UI Wowhead-Tooltips rendern kann.
- Die Casts/CD-Nutzung/Ausrüstung des Spielers mit den mitgelieferten Top-Log-
  Referenzspielern derselben Spec und desselben Bosses vergleichen und Deltas
  klar benennen.
- Keine Floskeln. Was passt, wird kurz unter "strengths" erwähnt.
- Keine Spellnamen, Itemnamen oder Zahlen erfinden.

Antworte ausschließlich in **gültigem JSON** im unten beschriebenen Schema —
kein Fließtext vor oder nach dem JSON-Objekt."""


JSON_SCHEMA_HINT = """Output JSON shape:
{
  "headline": "string (one sentence TL;DR)",
  "overall_score": 0-100,
  "role_focus": "dps" | "healer" | "tank",
  "strengths": ["short bullet", ...],
  "findings": [
    {
      "severity": "critical" | "high" | "medium" | "low" | "info",
      "title": "string",
      "detail": "1-3 sentences with numbers",
      "estimated_loss_pct": 0-100 or null,
      "category": "rotation" | "cooldowns" | "stats" | "talents" | "gear" | "trinkets" | "consumables" | "mechanics" | "other",
      "related_spell_ids": [int, ...],
      "related_item_ids": [int, ...]
    }, ...
  ],
  "rotation_summary": "string",
  "cooldown_usage_summary": "string",
  "stat_recommendations": "string",
  "talent_recommendations": "string",
  "gear_and_trinket_notes": "string",
  "comparison_to_top_logs": "string"
}

Sort findings so the most impactful ("critical") come first."""


def build_user_prompt(
    *,
    locale: Locale,
    role_focus: RoleFocus,
    fight_summary: dict[str, Any],
    player_summary: dict[str, Any],
    casts: list[dict[str, Any]],
    gear: list[dict[str, Any]],
    top_log_references: list[dict[str, Any]],
) -> str:
    """Build the user-side prompt with all the structured data the model needs."""
    lang = "Respond in English." if locale == "en" else "Antworte auf Deutsch."
    payload = {
        "fight": fight_summary,
        "player": player_summary,
        "top_casts": casts,
        "gear": gear,
        "top_log_references": top_log_references,
    }
    body = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    focus = (
        "Focus the analysis on healing throughput (HPS), mana usage and "
        "cooldown alignment with damage windows."
        if role_focus == "healer"
        else (
            "Focus on survival, damage taken vs. expected, active mitigation "
            "uptime, and threat — but still call out clear DPS gains."
            if role_focus == "tank"
            else "Focus the analysis on damage output (DPS), rotation accuracy and major cooldown usage."
        )
    )
    return (
        f"{lang}\n\n{focus}\n\n{JSON_SCHEMA_HINT}\n\n"
        "Below is the structured data for ONE player on ONE fight, plus reference "
        "top-log entries for the same spec/encounter. Use it to write the report.\n\n"
        f"DATA:\n```json\n{body}\n```"
    )


def system_prompt_for(locale: Locale) -> str:
    return SYSTEM_PROMPT_DE if locale == "de" else SYSTEM_PROMPT_EN
