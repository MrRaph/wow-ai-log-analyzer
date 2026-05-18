"""Parse simc's ``trait_data.inc`` into a queryable Python dataset.

The upstream file at https://github.com/simulationcraft/simc/blob/dragonflight/engine/dbc/generated/trait_data.inc
is generated from Blizzards DBC on every new WoW build, one C-record per
trait. We re-use it verbatim because it is the same dataset simcs own
binary uses to validate loadouts — so we are guaranteed the entry IDs we
produce will be accepted by simc unchanged.

Each record line looks like::

    { 1,  6, 117546,  94908, 1,  0, 122541,  100000,      0,      0,  1,  1, 100,
        "Death's Echo", {  250,  251,  252,    0 }, {    0,    0,    0,    0 },   0, 0 },

Fields (matching :type:`trait_data_t` in simc):

    tree_index, class_id, entry_id, node_id, max_ranks, req_points,
    definition_id, spell_id, replace_spell, override_spell,
    row, col, selection_index, name,
    id_spec[4], id_spec_starter[4], sub_tree_id, node_type

The dataset is loaded lazily from a configurable file path. In production
we ship the .inc file next to the package and pin it to the WoW build via
our existing ``wow_data`` refresh pipeline.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)


# simc talent_tree enum values (engine/sc_enums.hpp)
TREE_INVALID = 0
TREE_CLASS = 1
TREE_SPECIALIZATION = 2
TREE_HERO = 3
TREE_SELECTION = 4

# simc trait_node_type_e
NODE_NORMAL = 0
NODE_TIERED = 1
NODE_CHOICE = 2
NODE_SELECTION = 3


@dataclass(frozen=True)
class TraitEntry:
    """One row from ``trait_data.inc`` — corresponds to a single trait_data_t
    record. Each entry represents one *option* on a tree node (choice nodes
    have multiple entries for the same ``node_id``)."""

    tree_index: int
    class_id: int
    entry_id: int        # TraitNodeEntry.ID — what simc's class_talents= takes
    node_id: int         # TraitNode.ID — what Blizzards API returns as "id"
    max_ranks: int
    req_points: int
    definition_id: int   # TraitDefinition.ID — Blizzards "tooltip.talent.id"
    spell_id: int
    replace_spell: int
    override_spell: int
    row: int
    col: int
    selection_index: int
    name: str
    id_spec: tuple[int, ...]
    id_spec_starter: tuple[int, ...]
    sub_tree_id: int
    node_type: int


@dataclass
class TraitDataset:
    """The full set of traits for a single WoW build, plus pre-built lookup
    indices."""

    build: str
    entries: list[TraitEntry] = field(default_factory=list)

    # Indices populated by ``_build_indices``
    _by_entry_id: dict[int, TraitEntry] = field(default_factory=dict, repr=False)
    _by_class: dict[int, list[TraitEntry]] = field(default_factory=dict, repr=False)
    _node_to_entries: dict[int, list[TraitEntry]] = field(default_factory=dict, repr=False)
    _node_to_def: dict[tuple[int, int], TraitEntry] = field(default_factory=dict, repr=False)

    def _build_indices(self) -> None:
        self._by_entry_id.clear()
        self._by_class.clear()
        self._node_to_entries.clear()
        self._node_to_def.clear()
        for e in self.entries:
            self._by_entry_id[e.entry_id] = e
            self._by_class.setdefault(e.class_id, []).append(e)
            self._node_to_entries.setdefault(e.node_id, []).append(e)
            self._node_to_def[(e.node_id, e.definition_id)] = e

    # ---- queries --------------------------------------------------------

    def entries_for_class(self, class_id: int) -> list[TraitEntry]:
        return self._by_class.get(class_id, [])

    def entries_at_node(self, node_id: int) -> list[TraitEntry]:
        """All entries at a single node, in their original (selection_index)
        order. For non-choice nodes this is exactly one entry; for choice
        nodes it's the list the loadout-code's ``choice_index`` indexes
        into."""
        nodes = self._node_to_entries.get(node_id, [])
        return sorted(nodes, key=lambda e: (e.selection_index, e.entry_id))

    def entry_at(self, node_id: int, choice_index: int = 0) -> TraitEntry | None:
        nodes = self.entries_at_node(node_id)
        if not nodes:
            return None
        if 0 <= choice_index < len(nodes):
            return nodes[choice_index]
        return nodes[0]

    def find_entry_by_definition(
        self, node_id: int, definition_id: int
    ) -> TraitEntry | None:
        """Resolve Blizzards (node_id, definition_id) pair back to a concrete
        entry — needed when we get Blizzards expanded selections and want
        the matching simc entry_id."""
        return self._node_to_def.get((node_id, definition_id))

    def find_anchor_for_hero_tree(
        self, sub_tree_id: int, spec_id: int | None = None
    ) -> TraitEntry | None:
        """The gateway hero-talent entry for a sub-tree.

        Every hero-talent tree has exactly one "entry point" node at the
        top (``row == 1``) that the game grants on activation but
        omits from saved-loadout exports. Without it simc has the rest
        of the tree but no spell to root the chain on, which is what
        triggers the segfault on stale saved loadouts.

        We pick the matching gateway by lowest ``(row, col,
        selection_index)`` among the HERO entries for the sub-tree
        (optionally filtered to the given spec).
        """
        candidates: list[TraitEntry] = []
        for e in self.entries:
            if e.tree_index != TREE_HERO or e.sub_tree_id != sub_tree_id:
                continue
            if e.row <= 0 or e.col <= 0:
                continue
            if spec_id is not None and spec_id not in e.id_spec:
                continue
            candidates.append(e)
        if not candidates:
            return None
        candidates.sort(key=lambda e: (e.row, e.col, e.selection_index, e.entry_id))
        return candidates[0]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

# One full record per line in trait_data.inc:
#   { 1,  6, 117546,  94908, 1,  0, 122541, 100000, 0, 0, 1, 1, 100,
#     "Death's Echo", {  250, 251, 252, 0 }, { 0, 0, 0, 0 }, 0, 0 },
_RECORD_RE = re.compile(
    r"\{\s*"
    r"(?P<tree>-?\d+)\s*,\s*"
    r"(?P<class>-?\d+)\s*,\s*"
    r"(?P<entry>-?\d+)\s*,\s*"
    r"(?P<node>-?\d+)\s*,\s*"
    r"(?P<maxr>-?\d+)\s*,\s*"
    r"(?P<req>-?\d+)\s*,\s*"
    r"(?P<def>-?\d+)\s*,\s*"
    r"(?P<spell>-?\d+)\s*,\s*"
    r"(?P<repl>-?\d+)\s*,\s*"
    r"(?P<over>-?\d+)\s*,\s*"
    r"(?P<row>-?\d+)\s*,\s*"
    r"(?P<col>-?\d+)\s*,\s*"
    r"(?P<sel>-?\d+)\s*,\s*"
    # C string literal — handle escaped quotes
    r'"(?P<name>(?:[^"\\]|\\.)*)"\s*,\s*'
    r"\{\s*(?P<spec>[^}]*)\}\s*,\s*"
    r"\{\s*(?P<starter>[^}]*)\}\s*,\s*"
    r"(?P<sub>-?\d+)\s*,\s*"
    r"(?P<ntype>-?\d+)\s*\}",
    re.MULTILINE,
)

# Pulls the build string out of the first comment line:
#   // Player trait definitions, wow build 12.0.5.67602
_BUILD_RE = re.compile(r"wow build\s+(?P<build>[\d.]+)")


def _parse_int_list(s: str) -> tuple[int, ...]:
    return tuple(int(x.strip()) for x in s.split(",") if x.strip())


def parse_trait_data_inc(text: str) -> TraitDataset:
    """Parse the contents of ``trait_data.inc`` into a :class:`TraitDataset`."""
    build_match = _BUILD_RE.search(text)
    build = build_match["build"] if build_match else "unknown"
    entries: list[TraitEntry] = []
    for m in _RECORD_RE.finditer(text):
        try:
            entries.append(
                TraitEntry(
                    tree_index=int(m["tree"]),
                    class_id=int(m["class"]),
                    entry_id=int(m["entry"]),
                    node_id=int(m["node"]),
                    max_ranks=int(m["maxr"]),
                    req_points=int(m["req"]),
                    definition_id=int(m["def"]),
                    spell_id=int(m["spell"]),
                    replace_spell=int(m["repl"]),
                    override_spell=int(m["over"]),
                    row=int(m["row"]),
                    col=int(m["col"]),
                    selection_index=int(m["sel"]),
                    name=m["name"].encode().decode("unicode_escape"),
                    id_spec=_parse_int_list(m["spec"]),
                    id_spec_starter=_parse_int_list(m["starter"]),
                    sub_tree_id=int(m["sub"]),
                    node_type=int(m["ntype"]),
                )
            )
        except (ValueError, KeyError) as exc:
            logger.warning("trait_data.inc: skipping malformed record: %s", exc)
            continue
    ds = TraitDataset(build=build, entries=entries)
    ds._build_indices()
    return ds


def load_trait_data(path: str | Path) -> TraitDataset:
    """Read a ``trait_data.inc`` file from disk + parse it."""
    p = Path(path)
    return parse_trait_data_inc(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

# Default path: ship the .inc file alongside the package. The refresh
# pipeline writes a fresh copy here on every wow_data import.
_DEFAULT_PATH = Path(__file__).parent / "trait_data.inc"


@lru_cache(maxsize=1)
def get_dataset(path: str | Path | None = None) -> TraitDataset:
    """Process-wide singleton of the parsed trait dataset.

    The first call loads the file from ``path`` (or the default location);
    subsequent calls return the cached instance. Use :func:`reset_cache`
    to force a reload after a wow_data refresh.
    """
    src = Path(path) if path else _DEFAULT_PATH
    if not src.exists():
        raise FileNotFoundError(
            f"trait_data.inc not found at {src}. Run the wow_data refresh to "
            f"populate it, or copy the file from simc-source manually."
        )
    return load_trait_data(src)


def reset_cache() -> None:
    """Drop the cached dataset so the next ``get_dataset()`` call reloads."""
    get_dataset.cache_clear()
