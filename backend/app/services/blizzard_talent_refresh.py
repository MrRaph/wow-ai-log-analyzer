"""Refresh stale talent codes locally via :mod:`app.services.talents`.

The SimC Addon's ``/simc`` export persists saved loadouts from a frozen
snapshot that omits each hero-tree's gateway node (e.g. "Rider's
Champion" on Unholy DK). Activating the loadout in-game silently adds
it back; the exported text does not. SimulationCraft segfaults during
spell initialisation when fed those incomplete strings — there is no
graceful error path.

This module decodes each loadout the user picked against simcs own
trait dataset, auto-adds the missing hero-tree gateway, and emits a
``class_talents=/spec_talents=/hero_talents=`` block that simcs verbose
parser accepts. The verbose path also bypasses simcs internal
hero-tree validation that triggers the segfault on the base64 path.

If any step fails (corrupt code, dataset out of sync with the WoW
build, etc.) we fall back to the user's original string and let simc
surface the upstream error — better a clear "invalid talent string"
than a silent regression on a working loadout.
"""
from __future__ import annotations

import logging

from app.services.talents import (
    DecodedLoadout,
    build_talent_block,
    decode_loadout,
    get_dataset,
)
from app.services.talents.decoder import TalentDecodeError

logger = logging.getLogger(__name__)


def _extract_base64_code(text: str) -> str | None:
    """Pull the first ``talents=<base64>`` value from a multi-line block.

    Returns ``None`` if the input is already in the expanded form
    (``class_talents=`` etc.) — those don't need decoding.
    """
    for line in (text or "").splitlines():
        line = line.strip()
        if line.startswith("talents="):
            return line[len("talents=") :].strip()
    return None


def _active_talents_code(profile: str) -> str:
    """Find the uncommented ``talents=<code>`` line in a /simc paste.

    The in-game ``/simc`` command always emits exactly one such line for
    the currently-active loadout (alongside zero-or-more ``# Saved
    Loadout: …`` blocks). The active line is freshly re-serialised by
    the game on export and is the only string that's guaranteed to
    round-trip cleanly through simcs base64 decoder — including the
    spec-passive crossover entries from neighbouring hero trees that
    simcs verbose parser would otherwise reject as "extra talents".

    Returns ``""`` if no plain ``talents=`` line is present.
    """
    for line in (profile or "").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("talents="):
            return stripped[len("talents=") :].strip()
    return ""


def _decode(code: str) -> DecodedLoadout | None:
    try:
        dataset = get_dataset()
    except FileNotFoundError:
        logger.warning(
            "talent refresh: trait_data.inc not available — falling back to raw codes"
        )
        return None
    try:
        return decode_loadout(code, dataset=dataset)
    except TalentDecodeError as exc:
        logger.warning("talent refresh: cannot decode loadout: %s", exc)
        return None
    except Exception:  # noqa: BLE001 — defensive: never break the sim
        logger.exception("talent refresh: unexpected error decoding loadout")
        return None


async def refresh_loadout_talents(
    *,
    simc_profile: str,
    loadouts: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Return a copy of ``loadouts`` with each ``talents`` field replaced
    by an expanded ``class_talents=/spec_talents=/hero_talents=`` block
    that simc accepts.

    Loadouts whose ``talents`` field cant be decoded are passed through
    unchanged — the worker will then hit the same upstream simc error
    the user would have gotten without us, which is better than swapping
    in a wrong build silently.

    ``simc_profile`` is used to identify the *active* loadout — the
    uncommented ``talents=`` line in the paste — which we deliberately
    skip the decoder for. The active state is freshly re-serialised by
    the game on every ``/simc`` and is the only string that round-
    trips cleanly through simcs base64 path (including spec-passive
    crossover entries from neighbouring hero trees that our verbose
    output would reject as "Found N talents, expected M+1").

    Returns a NEW list — never mutates the caller's input.
    """
    active_code = _active_talents_code(simc_profile)

    refreshed: list[dict[str, object]] = []
    for ld in loadouts:
        if not isinstance(ld, dict):
            refreshed.append(ld)
            continue
        text = str(ld.get("talents") or "")
        code = _extract_base64_code(text)
        if not code:
            # Already in expanded form, or empty — pass through.
            refreshed.append(dict(ld))
            continue
        if active_code and code == active_code:
            # Active loadout: pass through unchanged. simcs base64
            # decoder accepts it cleanly, including the cross-tree
            # spec-passive talents the verbose path would reject.
            logger.info(
                "talent refresh: %r is the active loadout — skipping decode",
                ld.get("name") or "?",
            )
            refreshed.append(dict(ld))
            continue
        decoded = _decode(code)
        if decoded is None:
            refreshed.append(dict(ld))
            continue
        block = build_talent_block(decoded)
        if not block:
            # Decoder produced no entries (unlikely) — keep the raw code
            # so simc has *something* to chew on.
            refreshed.append(dict(ld))
            continue
        new_ld = dict(ld)
        new_ld["talents"] = block
        logger.info(
            "talent refresh: expanded loadout %r (spec=%d, %d selections, gateway_added=%s)",
            ld.get("name") or "?",
            decoded.spec_id,
            len(decoded.selections),
            decoded.anchor_added,
        )
        refreshed.append(new_ld)
    return refreshed
