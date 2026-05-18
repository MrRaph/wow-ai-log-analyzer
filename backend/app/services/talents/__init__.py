"""Talent loadout decoder + simc input generator.

Self-contained: parses Blizzard's base64 talent loadout codes against a
locally-cached copy of simc's ``trait_data.inc`` (the same data simc
itself uses, so we are guaranteed format-compatible).

Three responsibilities live here:

* :mod:`trait_data`  — load + query the trait dictionary
* :mod:`decoder`     — turn a base64 loadout code into selected entries
* :mod:`simc_input`  — render selected entries as
                       ``class_talents=`` / ``spec_talents=`` / ``hero_talents=``
                       lines that simc consumes
"""
from app.services.talents.trait_data import (
    TraitDataset,
    TraitEntry,
    get_dataset,
)
from app.services.talents.decoder import (
    DecodedLoadout,
    SelectedEntry,
    decode_loadout,
)
from app.services.talents.simc_input import (
    build_talent_block,
    tokenize,
)
from app.services.talents.encoder import encode_loadout

__all__ = [
    "DecodedLoadout",
    "SelectedEntry",
    "TraitDataset",
    "TraitEntry",
    "build_talent_block",
    "decode_loadout",
    "encode_loadout",
    "get_dataset",
    "tokenize",
]
