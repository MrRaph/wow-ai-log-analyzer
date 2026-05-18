"""Port of simcs ``generate_traits_hash`` to Python.

The inverse of :func:`decode_loadout`: takes a set of selected
``(entry_id, rank)`` pairs and produces the base64 loadout string
Blizzards game / API consume. The bit layout matches the decoder
exactly, so ``encode(decode(x)) == x`` for any well-formed loadout
hash — that round-trip is exactly how we verify the decoder is
correct.

We mainly need this to re-emit an *active-equivalent* hash after
decoding a stale saved loadout and adding the missing hero-tree
gateway. simcs ``talents=<hash>`` parser accepts the result, which is
the same path the game uses internally — closing the loop on the bug
chain (saved-loadout misses gateway ▶ stale ▶ segfault).
"""
from __future__ import annotations

from app.services.talents.decoder import _BitReader  # only for constants reuse
from app.services.talents.trait_data import (
    NODE_TIERED,
    TraitDataset,
    TraitEntry,
)


# Mirror the on-the-wire constants from simcs parse_traits_hash. Kept
# in lock-step with decoder.py via the shared get_dataset() build pin.
_BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_VERSION_BITS = 8
_SPEC_BITS = 16
_TREE_BITS = 128
_RANK_BITS = 6
_CHOICE_BITS = 2
_BYTE_SIZE = 6
_LOADOUT_SERIALIZATION_VERSION = 2


class _BitWriter:
    """LSB-first base64 writer. Mirrors simcs ``put_bit`` closure in
    generate_traits_hash."""

    __slots__ = ("_out", "_head", "_byte")

    def __init__(self) -> None:
        self._out: list[str] = []
        self._head = 0
        self._byte = 0

    def write(self, bits: int, value: int) -> None:
        for i in range(bits):
            bit_in_byte = self._head % _BYTE_SIZE
            self._head += 1
            self._byte += ((value >> min(i, 31)) & 1) << bit_in_byte
            if bit_in_byte == _BYTE_SIZE - 1:
                self._out.append(_BASE64_ALPHABET[self._byte])
                self._byte = 0

    def finish(self) -> str:
        # Flush trailing partial byte (mirrors the closing `if (head %
        # byte_size)` in simc).
        if self._head % _BYTE_SIZE:
            self._out.append(_BASE64_ALPHABET[self._byte])
        return "".join(self._out)


def _spec_class_id(spec_id: int, dataset: TraitDataset) -> int | None:
    for e in dataset.entries:
        if spec_id in e.id_spec:
            return e.class_id
    return None


def _ordered_class_nodes(class_id: int, dataset: TraitDataset) -> list[int]:
    nodes: set[int] = set()
    for e in dataset.entries_for_class(class_id):
        if e.tree_index < 1 or e.tree_index > 4:
            continue
        nodes.add(e.node_id)
    return sorted(nodes)


def _entries_at_node(node_id: int, class_id: int, dataset: TraitDataset) -> list[TraitEntry]:
    """Same view simcs ``generate_tree_nodes`` builds: every trait for
    this class+node, in trait-data declaration order (which matches
    selection_index for choice nodes).
    """
    return [e for e in dataset.entries_at_node(node_id) if e.class_id == class_id]


def encode_loadout(
    *,
    spec_id: int,
    selected: dict[int, int],
    dataset: TraitDataset,
    tree_hash_bits: list[int] | None = None,
) -> str:
    """Encode a set of ``(entry_id -> rank)`` selections into a base64
    loadout string.

    Parameters
    ----------
    spec_id
        Specialization id, the same value the decoder pulls out of the
        header.
    selected
        Mapping ``entry_id -> rank``. Entries not in this dict are
        treated as un-selected. Rank 0 is also un-selected (matches
        simcs encoder semantics).
    dataset
        Same trait dataset used for decoding — must be from the same
        WoW build, otherwise the node order changes and the resulting
        hash won't parse cleanly on the receiver side.
    """
    class_id = _spec_class_id(spec_id, dataset)
    if class_id is None:
        raise ValueError(f"spec {spec_id} not present in trait dataset")

    writer = _BitWriter()
    writer.write(_VERSION_BITS, _LOADOUT_SERIALIZATION_VERSION)
    writer.write(_SPEC_BITS, spec_id)
    # Tree hash: simc emits 128 zero bits to skip validation. We do the
    # same by default — the decoder ignores this block anyway. Callers
    # can pass ``tree_hash_bits`` to preserve a specific hash, useful
    # only when round-tripping a Blizzard-emitted code byte-for-byte.
    if tree_hash_bits is None:
        writer.write(_TREE_BITS, 0)
    else:
        if len(tree_hash_bits) != _TREE_BITS:
            raise ValueError(
                f"tree_hash_bits must have exactly {_TREE_BITS} entries"
            )
        for b in tree_hash_bits:
            writer.write(1, b & 1)

    for node_id in _ordered_class_nodes(class_id, dataset):
        entries = _entries_at_node(node_id, class_id, dataset)
        if not entries:
            writer.write(1, 0)  # not selected
            continue

        # Tiered nodes (mostly old class abilities pre-DF) sum ranks
        # across all entries on the node; everything else picks a
        # single entry. Mirror simcs encoder loop.
        rank = 0
        max_rank = 0
        init_rank = 0
        chosen_index = 0
        chosen_entry: TraitEntry | None = None
        is_choice = entries[0].node_type in (2, 3)  # NODE_CHOICE, NODE_SELECTION

        for i, entry in enumerate(entries):
            entry_rank = selected.get(entry.entry_id, 0)
            if entry.node_type == NODE_TIERED:
                rank += entry_rank
                max_rank += entry.max_ranks
                if entry_rank and chosen_entry is None:
                    chosen_entry = entry
                    chosen_index = i
            elif entry_rank:
                rank = entry_rank
                max_rank = entry.max_ranks
                init_rank = 1 if spec_id in entry.id_spec_starter else 0
                chosen_entry = entry
                chosen_index = i
                break

        if not rank:
            writer.write(1, 0)  # not selected
            continue
        writer.write(1, 1)  # selected

        # Purchased vs. granted-only. Granted entries are baseline-1
        # and we emit purchased=0 to make the receiver auto-rank them.
        if rank > init_rank:
            writer.write(1, 1)  # purchased
        else:
            writer.write(1, 0)
            continue

        # Partial vs. fully-allocated.
        if rank == max_rank:
            writer.write(1, 0)  # not partial
        else:
            writer.write(1, 1)
            writer.write(_RANK_BITS, rank)

        # Choice / selection flag.
        if is_choice:
            writer.write(1, 1)
            writer.write(_CHOICE_BITS, chosen_index)
        else:
            writer.write(1, 0)

    return writer.finish()
