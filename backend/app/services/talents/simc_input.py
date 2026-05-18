"""Render a :class:`DecodedLoadout` as simc-consumable text.

simc accepts talent input in two formats:

1. ``talents=<base64>`` — the full Blizzard loadout hash (segfaults on
   stale saved-loadout exports — see ``decoder.py`` docstring).
2. ``class_talents=<id_or_token>:<rank>/...`` plus the equivalent
   ``spec_talents=`` and ``hero_talents=`` lines — the verbose form
   that bypasses the base64 parser entirely. Same set of selected
   talents, different ingest path.

We emit form (2) because the base64 parser is the one with the
hero-tree-anchor bug on saved loadouts. The verbose path validates each
entry independently and resolves the anchor through the same
selection-node logic we synthesise in :func:`decode_loadout`.

``tokenize`` is a direct port of simcs ``util::tokenize`` — kept here
so the names we emit always match simcs internal lookup table even when
WoW renames a talent (lowercase + drop apostrophes / dashes / brackets /
non-ASCII; spaces become underscores). simc accepts entry-ids too, so
we prefer those — tokenize is the fallback for entries the dataset
flags as colliding-name.
"""
from __future__ import annotations

from app.services.talents.decoder import DecodedLoadout, SelectedEntry
from app.services.talents.trait_data import (
    TREE_CLASS,
    TREE_HERO,
    TREE_SELECTION,
    TREE_SPECIALIZATION,
)


def tokenize(name: str) -> str:
    """Mirror of simcs ``util::tokenize``.

    Rules (from ``engine/util/util.cpp``):
      * leading ``_`` or ``+`` characters are stripped
      * non-ASCII bytes are removed
      * alphabetic characters are lowercased
      * ``' '`` becomes ``'_'``
      * ``_ + . %`` and digits are kept
      * everything else (apostrophes, dashes, brackets, punctuation) is
        dropped — *not* converted to ``_``

    Examples::

        "Anti-Magic Zone"  -> "antimagic_zone"
        "Death's Reach"    -> "deaths_reach"
        "Rider's Champion" -> "riders_champion"
    """
    if not name:
        return ""
    # Strip leading _ or +
    while name and name[0] in "_+":
        name = name[1:]
    out: list[str] = []
    for ch in name:
        c = ord(ch)
        if c >= 0x80:
            continue
        if ch.isalpha():
            out.append(ch.lower())
        elif ch == " ":
            out.append("_")
        elif ch in "_+.%" or ch.isdigit():
            out.append(ch)
        # else: drop silently
    return "".join(out)


def build_talent_block(decoded: DecodedLoadout) -> str:
    """Render the decoded loadout as a multi-line simc input block.

    Output has three lines (or fewer, if a tree is empty)::

        class_talents=<entry>:<rank>/<entry>:<rank>/...
        spec_talents=...
        hero_talents=...

    The hero-tree selection anchor (added by ``decode_loadout``) lives
    in :attr:`SelectedEntry.tree_index == TREE_SELECTION` and is bundled
    onto the ``hero_talents=`` line — simcs verbose parser accepts
    selection-tree entries there.

    Granted-rank entries (e.g. baseline class abilities the game gives
    for free) are dropped from the output: simc adds them automatically
    and including them would force a needless rank validation pass.
    """
    by_tree: dict[int, list[str]] = {
        TREE_CLASS: [],
        TREE_SPECIALIZATION: [],
        TREE_HERO: [],
    }
    for sel in decoded.selections:
        if sel.is_granted:
            continue
        # Selection-tree entries (the hero-tree-anchor nodes) carry
        # spell_id=0 and simcs verbose parser rejects them — but simc
        # *auto-adds* them itself when it sees manual hero-tree entries
        # whose sub_tree wasnt parsed in. So drop them from our
        # output entirely.
        if sel.tree_index == TREE_SELECTION:
            continue
        if sel.tree_index not in by_tree:
            continue
        by_tree[sel.tree_index].append(_format_entry(sel))

    lines: list[str] = []
    if by_tree[TREE_CLASS]:
        lines.append("class_talents=" + "/".join(by_tree[TREE_CLASS]))
    if by_tree[TREE_SPECIALIZATION]:
        lines.append("spec_talents=" + "/".join(by_tree[TREE_SPECIALIZATION]))
    if by_tree[TREE_HERO]:
        lines.append("hero_talents=" + "/".join(by_tree[TREE_HERO]))
    return "\n".join(lines)


def _format_entry(sel: SelectedEntry) -> str:
    """One ``<entry_id>:<rank>`` token. We prefer the numeric entry id
    because simcs entry-id lookup is exact (no token collisions across
    same-named talents in different trees)."""
    return f"{sel.entry_id}:{sel.rank}"
