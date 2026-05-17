"""SimC sidecar — thin HTTP wrapper around the simc binary.

Endpoints
---------
GET  /healthz   liveness + simc bin path
GET  /version   simc git revision banner
POST /simulate  run one simulation and return parsed DPS + ability breakdown

Why a sidecar
-------------
We don't want simc shelled out from inside the backend container — that
would couple a 200+ MB C++ runtime to every backend image, and pulling
the upstream image gives us a daily-rebuilt binary that tracks WoW patch
data for free. The worker container hits this sidecar over the compose
network.

Rotation modes
--------------
A profile that came from the in-game ``/simc`` command never has
``actions=`` lines, so without further input simc auto-loads the
community-maintained default APL for the spec (near-optimal play).
For users who want to compare that against Blizzard's in-game
single-button-assist system we pass ``use_blizzard_action_list=1``,
which is simc's native switch for that mode (see the simc wiki
ActionLists page). When ``rotation == "blizzard"`` we also strip any
``actions=`` lines from the input as a belt-and-braces measure so a
user-edited profile can't accidentally override the flag.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("simc-sidecar")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)

# The upstream image installs simc on PATH. ``shutil.which`` finds it
# without us having to track wherever the upstream Dockerfile puts the
# binary across releases. ``SIMC_BIN`` env var overrides for debugging.
SIMC_BIN = os.environ.get("SIMC_BIN") or shutil.which("simc") or "/app/SimulationCraft/simc"

# Per-request timeout (seconds). Single-target 5000 iter on a fast box
# is typically 20-60s; M+ DungeonSlice can creep into minutes. 30 min
# is well over any realistic ceiling for our biggest fight profile.
SIM_TIMEOUT_S = int(os.environ.get("SIMC_TIMEOUT_S", "1800"))

# Optional cap on simc's internal thread pool. 0 / unset → simc decides
# (typically one per logical CPU). The prod box has many cores so we
# leave this on auto by default.
DEFAULT_THREADS = int(os.environ.get("SIMC_DEFAULT_THREADS", "0") or "0")

# Current-patch player consumable defaults. /simc paste from in-game
# normally has none of these, but the user expects us to assume "best
# raid prep" — full flask + food + augment rune + potion. These names
# track The War Within and must be updated when a new expansion ships
# (alongside SimC itself bumping its module's data tables). If a
# profile already sets one of these we keep the user's choice.
DEFAULT_CONSUMABLES: dict[str, str] = {
    "flask": "flask_of_alchemical_chaos_3",
    "food": "feast_of_the_divine_day",
    "augmentation": "crystallized",
    "potion": "tempered_potion_3",
    # Temporary weapon enchant. Honing rune is the current "best raid prep"
    # consumable. Some specs benefit more than others; simc picks correctly.
    "temporary_enchant": "main_hand:howling_rune_3/off_hand:howling_rune_3",
}

# Global sim flags we always set when the user asks us to "assume full
# raid prep". ``optimal_raid=1`` flips on every raid buff/debuff simc
# knows about. ``override.bloodlust=1`` makes sure Heroism/BL ticks
# even on fight styles that wouldn't otherwise grant it.
RAID_PREP_GLOBAL_FLAGS = (
    "optimal_raid=1",
    "override.bloodlust=1",
)

app = FastAPI(title="simc-sidecar")


class SimulateRequest(BaseModel):
    profile: str = Field(..., description="Full SimC profile text (.simc input).")
    fight_style: str = Field("Patchwerk", description="simc fight_style flag.")
    desired_targets: int = Field(1, ge=1, le=20)
    iterations: int = Field(5000, ge=100, le=50000)
    target_error: float | None = Field(
        None,
        ge=0.0,
        le=5.0,
        description="If set, simc stops once DPS std-error falls below this %.",
    )
    threads: int | None = Field(None, ge=1, le=256)
    rotation: str = Field(
        "simc_default",
        pattern="^(simc_default|blizzard|custom)$",
        description=(
            "simc_default = community APL (default when profile has no "
            "actions= lines), blizzard = Blizzard in-game single-button "
            "assist via use_blizzard_action_list=1, custom = use whatever "
            "actions= lines the profile already contains."
        ),
    )
    assume_raid_prep: bool = Field(
        True,
        description=(
            "If true, force optimal_raid=1 + bloodlust override and inject "
            "current-patch flask/food/augment-rune/potion defaults for any "
            "consumable the profile doesn't already specify. Matches the "
            "expectation that we sim a fully prepped character."
        ),
    )


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"ok": True, "simc_bin": SIMC_BIN, "exists": Path(SIMC_BIN).exists()}


@app.get("/version")
async def version() -> dict[str, Any]:
    """Probe simc's banner. We pass a trivial spell_query to make simc
    print its header and exit quickly without spinning up a sim."""
    if not Path(SIMC_BIN).exists():
        raise HTTPException(503, f"simc binary not found at {SIMC_BIN}")
    proc = await asyncio.create_subprocess_exec(
        SIMC_BIN,
        "spell_query=spell.id=1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=30)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(504, "simc version probe timed out")
    text = (out or b"").decode("utf-8", "replace")
    banner = next(
        (ln.strip() for ln in text.splitlines() if ln.strip().startswith("SimulationCraft")),
        "",
    )
    return {"banner": banner, "exit_code": proc.returncode}


def _strip_action_lines(profile: str) -> str:
    """Drop any ``actions[+]=`` line so the engine falls back to its
    built-in default APL (community default or Blizzard one-button,
    depending on the other flags we pass)."""
    kept: list[str] = []
    for line in profile.splitlines():
        head = line.lstrip().split("=", 1)[0].split("#", 1)[0].strip()
        if head.startswith("actions"):
            continue
        kept.append(line)
    return "\n".join(kept)


def _has_directive(profile: str, key: str) -> bool:
    """Return True if the profile already sets ``key=…`` (anywhere,
    ignoring lines commented out with ``#``)."""
    needle = f"{key}="
    for line in profile.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.split("=", 1)[0].strip() == key:
            return True
    return False


def _inject_consumable_defaults(profile: str) -> str:
    """Append flask/food/augment/potion lines for any consumable the
    profile doesn't already define. Keeps the user's choice if they
    already set one — we only fill gaps."""
    missing = [
        f"{key}={value}"
        for key, value in DEFAULT_CONSUMABLES.items()
        if not _has_directive(profile, key)
    ]
    if not missing:
        return profile
    suffix = "\n\n# raid prep defaults injected by simc-sidecar\n" + "\n".join(missing) + "\n"
    return profile.rstrip() + suffix


def _parse_result(data: dict, fallback_dps_mean: float = 0.0) -> dict[str, Any]:
    """Pull the bits we care about out of simc's JSON dump (--json2).

    simc's JSON is verbose (hundreds of KiB per sim) — we keep only
    the DPS summary and per-ability damage breakdown. The frontend
    renders both directly.
    """
    sim = data.get("sim") or {}
    players = sim.get("players") or []
    if not players:
        raise ValueError("no players in simc output")
    player = players[0]
    collected = player.get("collected_data") or {}

    def _stat(field: str, key: str = "mean") -> float:
        node = collected.get(field) or {}
        return float(node.get(key, 0.0) or 0.0)

    dps_mean = _stat("dps") or fallback_dps_mean
    fight_length = _stat("fight_length")

    abilities: list[dict[str, Any]] = []
    for stats in player.get("stats") or []:
        # simc emits a row per spell *per type* (damage, heal, …) plus
        # rollup rows. We only want damage and we want the per-spell
        # entries (skip the synthetic "total" / class roll-ups marked
        # with type != damage).
        if (stats.get("type") or "").lower() != "damage":
            continue
        actual = stats.get("actual_amount") or {}
        per_iter_damage = float(actual.get("mean", 0.0) or 0.0)
        if per_iter_damage <= 0:
            continue
        per_ability_dps = per_iter_damage / fight_length if fight_length else 0.0
        abilities.append(
            {
                "name": stats.get("name") or "",
                "school": stats.get("school") or "",
                "damage_per_iter": per_iter_damage,
                "dps": per_ability_dps,
                "executes": float((stats.get("num_executes") or {}).get("mean", 0.0) or 0.0),
                "hits": float((stats.get("num_direct_results") or {}).get("mean", 0.0) or 0.0),
                "crit_pct": float(stats.get("portion_amount", 0.0) or 0.0) * 100.0,
            }
        )
    abilities.sort(key=lambda x: x["dps"], reverse=True)
    total_dps = sum(a["dps"] for a in abilities) or dps_mean
    for a in abilities:
        a["pct"] = (a["dps"] / total_dps * 100.0) if total_dps else 0.0

    return {
        "dps_mean": dps_mean,
        "dps_min": _stat("dps", "min"),
        "dps_max": _stat("dps", "max"),
        "dps_stddev": _stat("dps", "std_dev"),
        "fight_length_mean": fight_length,
        "iterations": sim.get("iterations"),
        "target_error_actual": (sim.get("target_error") or {}).get("dps")
        if isinstance(sim.get("target_error"), dict)
        else None,
        "build_version": (
            (data.get("version") or {}).get("git_revision")
            or sim.get("build_version")
            or data.get("build_version")
        ),
        "player_name": player.get("name"),
        "player_spec": player.get("specialization") or player.get("talent_tree"),
        "player_class": player.get("class"),
        "abilities": abilities,
    }


@app.post("/simulate")
async def simulate(req: SimulateRequest) -> dict[str, Any]:
    if not Path(SIMC_BIN).exists():
        raise HTTPException(503, f"simc binary not found at {SIMC_BIN}")

    profile_text = req.profile
    extra_args: list[str] = []
    if req.rotation == "blizzard":
        # Strip user actions first so the engine can't ignore the flag,
        # then turn on Blizzard's in-game single-button-assist system.
        profile_text = _strip_action_lines(profile_text)
        extra_args.append("use_blizzard_action_list=1")
    elif req.rotation == "simc_default":
        # The community default APL kicks in automatically when the
        # profile has no actions= lines. /simc paste from in-game
        # never includes any, but a user-edited profile might — strip
        # to make the mode predictable.
        profile_text = _strip_action_lines(profile_text)
    # custom → leave the profile alone

    if req.assume_raid_prep:
        profile_text = _inject_consumable_defaults(profile_text)
        extra_args.extend(RAID_PREP_GLOBAL_FLAGS)

    with tempfile.TemporaryDirectory(prefix="simc-") as workdir:
        wd = Path(workdir)
        input_file = wd / "input.simc"
        json_out = wd / "out.json"
        input_file.write_text(profile_text, encoding="utf-8")

        args: list[str] = [
            SIMC_BIN,
            str(input_file),
            f"iterations={req.iterations}",
            f"fight_style={req.fight_style}",
            f"desired_targets={req.desired_targets}",
            "html=",
            f"json2={json_out}",
        ]
        if req.target_error is not None:
            args.append(f"target_error={req.target_error}")
        threads = req.threads if req.threads is not None else DEFAULT_THREADS
        if threads:
            args.append(f"threads={threads}")
        args.extend(extra_args)

        logger.info(
            "simc spawn: fight=%s targets=%s iter=%s rotation=%s",
            req.fight_style,
            req.desired_targets,
            req.iterations,
            req.rotation,
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(wd),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=SIM_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                raise HTTPException(504, f"simc timed out after {SIM_TIMEOUT_S}s")
        except FileNotFoundError as exc:
            raise HTTPException(503, f"failed to spawn simc: {exc}")

        out_text = (stdout or b"").decode("utf-8", "replace")
        err_text = (stderr or b"").decode("utf-8", "replace")
        if proc.returncode != 0:
            raise HTTPException(
                400,
                f"simc exit {proc.returncode}: {(err_text or out_text)[-1500:]}",
            )
        if not json_out.exists():
            raise HTTPException(500, f"simc finished but produced no JSON: {out_text[-800:]}")

        try:
            with json_out.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise HTTPException(500, f"could not decode simc JSON: {exc}")

        try:
            parsed = _parse_result(data)
        except ValueError as exc:
            raise HTTPException(500, f"could not parse simc JSON: {exc}")

        # Keep a short tail of simc's stdout for diagnostics — full
        # log is megabytes and not useful in the DB row.
        parsed["log_tail"] = out_text[-2000:]
        return parsed


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
