"""Unit tests for the local talent-loadout decoder.

Test corpus: real ``/simc`` saved-loadout exports captured during the
hero-tree-gateway investigation, plus the matching ``ACTIVE``-state
exports the user produced by activating each loadout in-game and
re-running ``/simc``. Decoded entries from a SAVED loadout (after
gateway-auto-fix) MUST equal the decoded entries from its matching
ACTIVE export — that's the whole point of the workaround.
"""
from __future__ import annotations

import pytest

from app.services.talents import (
    build_talent_block,
    decode_loadout,
    get_dataset,
    tokenize,
)
from app.services.talents.decoder import TalentDecodeError
from app.services.talents.trait_data import (
    NODE_SELECTION,
    TREE_HERO,
    TREE_SELECTION,
)


# ---------------------------------------------------------------------------
# tokenize — port of simcs util::tokenize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Spaces become underscores, alphanumerics lowercased.
        ("Death Strike", "death_strike"),
        ("Outbreak", "outbreak"),
        # Apostrophes are *removed*, not converted to underscore.
        ("Death's Reach", "deaths_reach"),
        ("Rider's Champion", "riders_champion"),
        ("Mograine's Might", "mograines_might"),
        # Dashes are removed too — "anti_magic_zone" would NOT match.
        ("Anti-Magic Zone", "antimagic_zone"),
        ("Anti-Magic Barrier", "antimagic_barrier"),
        # Brackets and other punctuation: dropped.
        ("Test (Foo)", "test_foo"),
        # Leading underscores and pluses are stripped.
        ("__leading", "leading"),
        ("++plus_start", "plus_start"),
        # Digits and dots/percents are kept.
        ("Tier 23", "tier_23"),
        ("50%", "50%"),
        # Empty / pure-junk input.
        ("", ""),
        ("---", ""),
    ],
)
def test_tokenize_matches_simc(raw: str, expected: str) -> None:
    assert tokenize(raw) == expected


# ---------------------------------------------------------------------------
# Decoder — real loadout codes from the investigation
# ---------------------------------------------------------------------------


# Unholy DK Deadfox — paste saved code + the matching active export
# captured after manually activating the loadout in-game.
DEADFOX_PAIRS = [
    (
        "San Layn Dragons",
        "CwPAkXBWxkyfx9CbGaHonEAhLBwMMjZGDz2MzMjZzMjZmxAAAAAAAAwMjZMAYZYmZzMzMzMGYgZsxYZBw2gNMgZAYMzMMYmBzYMA",
        "CwPAkXBWxkyfx9CbGaHonEAhLBwMMjZGDz2MzMTzmZGzMjBAAAAAAAgZGzYAwywMzmZmZmZMwAzYTjlFAbTshBMDAjZmhBzMYGjB",
    ),
    (
        "Riders Vanguard",
        "CwPAkXBWxkyfx9CbGaHonEAhLBwMjZMzYY2mZmZMbmZMmxAAAAAAAAwMDjBALzYmZbmZMmBsZWMMwAzGDGLYAzAwYmZMDwMzMGD",
        "CwPAkXBWxkyfx9CbGaHonEAhLBwMjZMzYY2mZmZa2MzYMjBAAAAAAAgZGGDAWmxMz2MzYMDYzsYYIDMbM0YBDYGAGzMjZAmZmxYA",
    ),
    (
        "Riders ST / Raid",
        "CwPAkXBWxkyfx9CbGaHonEAhLBwMjZMDDz2MzMjZzMzMmxAAAAAAAAwMDzMAYbGzMbzMjxMgNzihBGY2YwYBAzAwYmZMDwMzMGD",
        "CwPAkXBWxkyfx9CbGaHonEAhLBwMjZMDDz2MzMTzmZmZMjBAAAAAAAgZGmZAw2MmZ2mZGjZAbmFDDZgZjhGLAYGAGzMjZAmZmxYA",
    ),
    (
        "Riiders AOE / M+",
        "CwPAkXBWxkyfx9CbGaHonEAhLBYmZMPgxYY2GzMjZbmZMzMGAAAAAAAAmZMMAYZGzMbmZMzMgFzihBGY2YwYBDYGAGzMjZAmZGzYA",
        "CwPAkXBWxkyfx9CbGaHonEAhLBYmZMPgxYY2GzMTz2MzYmZMAAAAAAAAMzYYAwyMmZ2MzYmZALmFDDZgZjhGLYAzAwYmZMDwMzYGD",
    ),
]


@pytest.fixture(scope="module")
def dataset():
    return get_dataset()


@pytest.mark.parametrize("label,saved_code,active_code", DEADFOX_PAIRS, ids=lambda v: v if isinstance(v, str) else "")
def test_saved_loadout_decodes_to_same_user_picked_entries_as_active(
    dataset, label: str, saved_code: str, active_code: str
) -> None:
    """User-picked talents (i.e. ``is_granted == False``) decoded from a
    SAVED loadout must equal those decoded from its ACTIVE re-export.
    Granted talents are auto-added by simc on either path and are
    encoded differently by saved vs. active streams, so they're
    excluded from this comparison."""
    saved = decode_loadout(saved_code, dataset=dataset)
    active = decode_loadout(active_code, dataset=dataset)

    saved_pairs = {(s.entry_id, s.rank) for s in saved.selections if not s.is_granted}
    active_pairs = {(s.entry_id, s.rank) for s in active.selections if not s.is_granted}

    only_in_saved = saved_pairs - active_pairs
    only_in_active = active_pairs - saved_pairs

    # The auto-added hero-tree gateway (e.g. (117663, 1) for Rider) is
    # the *only* tolerated mismatch — its an entry the game grants on
    # activation but doesn't serialise into the saved snapshot.
    assert len(only_in_saved) <= 1, (
        f"{label}: more than the gateway differs between SAVED and ACTIVE: "
        f"{sorted(only_in_saved)}"
    )
    # Active's extra entries vs saved are typically the same gateway
    # serialised differently (purchased=false on the active stream =>
    # is_granted=True, which we already filtered out). If anything else
    # leaks through, it's a genuine encoder discrepancy.
    assert not only_in_active, (
        f"{label}: entries selected only in ACTIVE-decoded loadout, missing from SAVED: "
        f"{sorted(only_in_active)}"
    )


@pytest.mark.parametrize("label,saved_code,active_code", DEADFOX_PAIRS, ids=lambda v: v if isinstance(v, str) else "")
def test_decoded_loadouts_produce_non_empty_simc_blocks(
    dataset, label: str, saved_code: str, active_code: str
) -> None:
    """End-of-pipeline check: every SAVED loadout in the test corpus
    must produce a complete simc input block (all three talent lines).
    This is what guarantees the simc-Midnight segfault is bypassed —
    simcs verbose parser refuses partial blocks."""
    for code in (saved_code, active_code):
        block = build_talent_block(decode_loadout(code, dataset=dataset))
        for required in ("class_talents=", "spec_talents=", "hero_talents="):
            assert required in block, f"{label}: missing '{required}' in simc block"


def test_decoded_saved_loadout_has_hero_gateway(dataset) -> None:
    """Saved loadouts omit the hero-tree gateway node; the decoder must
    detect that and synthesise it (otherwise simc segfaults)."""
    _, saved_code, _ = DEADFOX_PAIRS[3]  # AOE/M+, hero tree = Rider (32)
    decoded = decode_loadout(saved_code, dataset=dataset)
    assert decoded.anchor_added, "Saved AOE/M+ loadout should trigger gateway auto-add"
    # Rider's Champion is entry 117663 on node 95066.
    gateway_present = any(
        s.entry_id == 117663 for s in decoded.selections
    )
    assert gateway_present, "Rider's Champion gateway entry should be in selections"


def test_decoded_active_loadout_does_not_re_add_gateway(dataset) -> None:
    """The auto-fix is idempotent: ACTIVE exports already include the
    gateway, so anchor_added must stay False."""
    _, _, active_code = DEADFOX_PAIRS[3]
    decoded = decode_loadout(active_code, dataset=dataset)
    assert decoded.anchor_added is False


def test_decoder_rejects_garbage_codes(dataset) -> None:
    with pytest.raises(TalentDecodeError):
        decode_loadout("", dataset=dataset)
    with pytest.raises(TalentDecodeError):
        decode_loadout("!!!not_base64!!!", dataset=dataset)


def test_decoded_spec_matches_paste(dataset) -> None:
    """Spec id 252 = Unholy DK on every Deadfox paste."""
    for _, saved_code, _ in DEADFOX_PAIRS:
        assert decode_loadout(saved_code, dataset=dataset).spec_id == 252


# ---------------------------------------------------------------------------
# build_talent_block — simc input generator
# ---------------------------------------------------------------------------


def test_talent_block_has_three_sections(dataset) -> None:
    _, saved_code, _ = DEADFOX_PAIRS[3]
    block = build_talent_block(decode_loadout(saved_code, dataset=dataset))
    assert block.count("class_talents=") == 1
    assert block.count("spec_talents=") == 1
    assert block.count("hero_talents=") == 1


def test_talent_block_omits_selection_entries(dataset) -> None:
    """SELECTION-tree entries (hero-tree-anchor nodes) carry spell_id=0
    and simcs verbose parser rejects them. They must not appear in
    the output — simc auto-adds them itself based on the manual hero
    entries."""
    _, saved_code, _ = DEADFOX_PAIRS[3]
    decoded = decode_loadout(saved_code, dataset=dataset)
    # Find the Rider SELECTION-node entries (node 99820 on Unholy DK)
    selection_entry_ids = {
        e.entry_id for e in dataset.entries
        if e.tree_index == TREE_SELECTION and e.sub_tree_id == 32
    }
    assert selection_entry_ids, "test bug: dataset is missing the Rider SELECTION entries"
    block = build_talent_block(decoded)
    for eid in selection_entry_ids:
        assert f"{eid}:" not in block, (
            f"SELECTION entry {eid} leaked into the simc block — simc will reject it"
        )


def test_hero_gateway_lands_on_hero_talents_line(dataset) -> None:
    """The auto-added gateway is a HERO-tree entry, so it must end up in
    ``hero_talents=`` (not ``class_talents=`` or its own line)."""
    _, saved_code, _ = DEADFOX_PAIRS[3]
    block = build_talent_block(decode_loadout(saved_code, dataset=dataset))
    hero_line = next(
        (l for l in block.splitlines() if l.startswith("hero_talents=")), ""
    )
    assert "117663:" in hero_line, "Rider's Champion (entry 117663) should be on hero_talents="


# ---------------------------------------------------------------------------
# Karatepummel (Monk Windwalker) — different class, different hero tree
# ---------------------------------------------------------------------------


KARATEPUMMEL_SAVED_CODES = [
    # (label, saved_code, expected_spec_id, expected_sub_tree_id)
    ("Raid Vang",  "C0QAi6cZM+HWADeySjzG9Lwx8PzYMYMYbmZ2mxAAAAAAAAAAAALDDYGGGwMGmZmZYWGmhZZGAALmZbMMmZGAAbAwsMLmZmZBYYgZGAGLjBMgB", 269, 65),
    ("SP M+ v3",   "C0QAi6cZM+HWADeySjzG9Lwx8PzYMYMYbmZ2mxAAAAAAAAAAAALDzAzwwAGmxMzMDzGmhZZGAALmZbMMmZGAAbAwsMLmZmZBYMDMzAwYZAMgB", 269, 65),
    ("crown",      "C0QAi6cZM+HWADeySjzG9Lwx8PzYw2MGsNzMbzAAAAAAAAAAAAsMMgZsNMgZMMzMzwsMMDzyMAA2Mz2YYmZmBAwGAMLziZmZWAwAzMAwyYADYA", 269, 65),
]


@pytest.mark.parametrize("label,code,spec_id,sub_tree_id", KARATEPUMMEL_SAVED_CODES, ids=lambda v: v if isinstance(v, str) else "")
def test_karatepummel_loadouts_decode_cleanly(
    dataset, label: str, code: str, spec_id: int, sub_tree_id: int
) -> None:
    decoded = decode_loadout(code, dataset=dataset)
    assert decoded.spec_id == spec_id
    # Loadout should contain HERO entries for the picked sub-tree.
    hero_picks = [s for s in decoded.selections if s.tree_index == TREE_HERO]
    assert hero_picks, "Loadout had no hero talents at all"
    sub_trees = {s.sub_tree_id for s in hero_picks if s.sub_tree_id > 0}
    assert sub_tree_id in sub_trees, (
        f"{label}: expected hero sub-tree {sub_tree_id}, got {sub_trees}"
    )


def test_karatepummel_saved_to_simc_block_no_exceptions(dataset) -> None:
    """All three Karatepummel saved loadouts must produce a non-empty
    simc block without raising."""
    for label, code, _, _ in KARATEPUMMEL_SAVED_CODES:
        block = build_talent_block(decode_loadout(code, dataset=dataset))
        assert "class_talents=" in block
        assert "spec_talents=" in block
        assert "hero_talents=" in block


# ---------------------------------------------------------------------------
# TIERED-node regression: rank-splitting across entries
# ---------------------------------------------------------------------------


def test_tiered_node_rank_is_split_across_entries(dataset) -> None:
    """Dêadfox's AOE/M+ loadout fully-allocates "Commander of the Dead" —
    a TIERED node where simc distributes the 4 picked ranks across three
    entries (ids 136918/136919/136920). Our decoder must do the same;
    aggregating them into a single ``136920:4`` entry would make simc
    cap the rank at max_ranks=1 and silently drop 3 ranks (and ~25%
    DPS). The fix matches simcs ``parse_traits_hash`` behaviour.
    """
    saved_code = DEADFOX_PAIRS[3][1]  # Riiders AOE / M+ saved
    decoded = decode_loadout(saved_code, dataset=dataset)
    tiered = {136918, 136919, 136920}
    found = {s.entry_id: s.rank for s in decoded.selections if s.entry_id in tiered}
    # Each entry of the TIERED chain must show up at least once with
    # rank > 0; the aggregate must hit max_ranks of the chain (each
    # entry has max_ranks=1 except possibly the middle 2-rank one).
    assert tiered.issubset(set(found)), (
        f"all three tiered entries should be present, got {sorted(found)}"
    )
    # The full ranks-allocated total stays the same as the base64 stream
    # encoded — sum of per-entry ranks must equal the original picks.
    assert sum(found.values()) == 4, (
        f"expected 4 ranks distributed across the tiered chain, got {found}"
    )
