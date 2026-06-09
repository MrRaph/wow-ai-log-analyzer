"""Unit tests for the WCL URL/code parser and small response shapers."""
from __future__ import annotations

import pytest

from app.core.errors import ValidationAppError
from app.services.wcl.parser import (
    _flavor_to_game_version,
    class_slug_from_wcl,
    parse_report_input_details,
    parse_report_input,
    role_from_spec_slug,
    spec_slug_from_wcl,
)


@pytest.mark.parametrize(
    "value",
    [
        "AbCdEfGhIjKlMnOp",
        "https://www.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp",
        "https://www.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp#fight=12",
        "https://classic.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp",
        "https://fresh.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp",
        "  https://www.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp/  ",
    ],
)
def test_parse_report_input_valid(value):
    assert parse_report_input(value) == "AbCdEfGhIjKlMnOp"


@pytest.mark.parametrize("value", ["", "totally-not-a-code", "https://example.com/", None])
def test_parse_report_input_invalid(value):
    with pytest.raises((ValidationAppError, AttributeError, TypeError)):
        parse_report_input(value)  # type: ignore[arg-type]


def test_class_and_spec_slugs():
    assert class_slug_from_wcl("DemonHunter") == "demon_hunter"
    assert class_slug_from_wcl("Death Knight") == "death_knight"
    assert spec_slug_from_wcl("priest", "Holy") == "priest_holy"
    assert spec_slug_from_wcl("hunter", "BeastMastery") == "hunter_beast_mastery"
    assert spec_slug_from_wcl("hunter", "Beast Mastery") == "hunter_beast_mastery"


def test_role_inference():
    assert role_from_spec_slug("priest_holy") == "healer"
    assert role_from_spec_slug("paladin_protection") == "tank"
    assert role_from_spec_slug("mage_fire") == "dps"
    assert role_from_spec_slug("unknown_thing", fallback="dps") == "dps"


@pytest.mark.parametrize(
    ("value", "flavor"),
    [
        ("AbCdEfGhIjKlMnOp", "retail"),
        ("https://www.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp", "retail"),
        ("https://classic.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp", "classic"),
        ("https://fresh.warcraftlogs.com/reports/AbCdEfGhIjKlMnOp", "fresh"),
    ],
)
def test_parse_report_input_details_flavor(value, flavor):
    code, parsed_flavor = parse_report_input_details(value)
    assert code == "AbCdEfGhIjKlMnOp"
    assert parsed_flavor == flavor


# ---------------------------------------------------------------------------
# _flavor_to_game_version — expansion_id routing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("flavor", "expansion_id", "expected"),
    [
        # Retail ignores expansion_id entirely.
        ("retail", None, "retail"),
        ("retail", 2,    "retail"),
        # Classic subdomain: expansion_id drives the slug.
        ("classic", None, "classic"),   # no id → fall back to vanilla
        ("classic", 1,    "classic"),   # Classic Era
        ("classic", 2,    "tbc"),       # The Burning Crusade
        ("classic", 3,    "wotlk"),     # Wrath of the Lich King
        ("classic", 4,    "cata"),      # Cataclysm
        ("classic", 5,    "mop"),       # Mists of Pandaria
        ("classic", 99,   "classic"),   # Unknown id → fall back to vanilla
        # Fresh subdomain: same expansion_id logic — SoD can host TBC content.
        ("fresh",   None, "classic"),   # no id → Classic Era default
        ("fresh",   1,    "classic"),   # Classic Era / SoD Season 1
        ("fresh",   2,    "tbc"),       # SoD / Fresh server in TBC phase
        ("fresh",   3,    "wotlk"),     # hypothetical WotLK Fresh
        ("fresh",   99,   "classic"),   # Unknown id → fall back to vanilla
    ],
)
def test_flavor_to_game_version(flavor, expansion_id, expected):
    assert _flavor_to_game_version(flavor, expansion_id) == expected
