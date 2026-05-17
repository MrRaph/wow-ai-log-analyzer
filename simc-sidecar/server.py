"""SimC sidecar — async-job HTTP wrapper around the simc binary.

Endpoints
---------
GET    /healthz             liveness + simc bin path
GET    /version             simc git revision banner
POST   /simulate            queue a simulation; returns 202 + {job_id}
GET    /jobs/{job_id}       poll status / fetch result
GET    /jobs                list active + recently-finished jobs
DELETE /jobs/{job_id}       cancel a queued/running job (best-effort)

Why a job queue instead of a synchronous POST
---------------------------------------------
A single simc run can take 30 s to 5 min and pins every available CPU.
Holding the HTTP connection open the whole time blocks the caller (the
backend arq worker), and serving more than one simc at a time on the
same box just thrashes the CPU cache.

The queue lets us decouple submission from execution and apply a
concurrency cap (``SIMC_MAX_CONCURRENT``, default 1). Multiple backend
workers submitting in parallel each get an immediate ``202`` and a
job_id; the sidecar serialises execution and the workers poll on a
short interval. Finished jobs stay in memory for ``SIMC_JOB_RETENTION_S``
(default 1 h) so the poll can still fetch results after completion.

Rotation modes
--------------
A /simc paste from in-game never has ``actions=`` lines, so without
further input simc auto-loads the community-maintained default APL for
the spec (near-optimal play). For users who want to compare against
Blizzard's in-game single-button-assist system we pass
``use_blizzard_action_list=1`` (simc wiki: ActionLists page). When
``rotation == "blizzard"`` we also strip any ``actions=`` lines from the
input as belt-and-braces.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import shutil
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

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
# is typically 20-60 s; M+ DungeonSlice can creep into minutes. 30 min
# is well over any realistic ceiling for our biggest fight profile.
SIM_TIMEOUT_S = int(os.environ.get("SIMC_TIMEOUT_S", "1800"))

# Optional cap on simc's internal thread pool. 0 / unset → simc decides
# (typically one per logical CPU). The prod box has many cores so we
# leave this on auto by default.
DEFAULT_THREADS = int(os.environ.get("SIMC_DEFAULT_THREADS", "0") or "0")

# How many simulations may run *simultaneously* inside this sidecar.
# Default 1 because each simc uses every available core; two concurrent
# sims would halve both throughputs without improving wall-clock. Bump
# this if you ever cap ``SIMC_DEFAULT_THREADS`` to a fraction of CPUs.
MAX_CONCURRENT = int(os.environ.get("SIMC_MAX_CONCURRENT", "1") or "1")

# How long to keep finished/failed jobs in memory so the backend's poll
# can still pick up the result after the run completed. 1 h is plenty;
# the backend usually polls within a few seconds of completion.
JOB_RETENTION_S = int(os.environ.get("SIMC_JOB_RETENTION_S", "3600") or "3600")

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
    # NOTE: temporary_enchant is intentionally NOT defaulted. The right
    # choice is spec-specific (DK runeforge, Rogue poison, weapon oil for
    # casters, etc.) and the previously-bundled Howling Rune was actually
    # ilvl-capped at 120 — silently inactive on any current-tier weapon
    # and the source of confusing "requires a maximum ilevel of 120"
    # warnings. We let the /simc paste provide it (or omit it).
}

# Sim flags for "assume full raid prep" — only applied to raid-shaped
# fight styles (Patchwerk, Ultraxion, …). ``optimal_raid=1`` flips on
# every standard raid buff/debuff and ``override.bloodlust=1`` makes
# sure Heroism/Bloodlust is up for the whole fight (raid bosses
# practically always get one).
#
# For DungeonSlice we deliberately DON'T apply these: simc's tuned M+
# profile already models a 5-player group with the right buff coverage
# and a single Bloodlust at pull start. Forcing optimal_raid + a
# permanent BL on top of that overstates Mythic+ DPS by a chunk.
RAID_PREP_GLOBAL_FLAGS = (
    "optimal_raid=1",
    "override.bloodlust=1",
)

# Fight styles that we treat as "raid encounter" (full raid prep).
# DungeonSlice is intentionally absent — see the comment above.
_RAID_PREP_FIGHT_STYLES = {"patchwerk", "ultraxion", "lightmovement"}

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


@dataclass
class Job:
    id: str
    status: JobStatus = "queued"
    request: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    log_tail: str = ""
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    task: asyncio.Task | None = None


# Jobs live in process memory. Keyed by job_id. The lock guards writes;
# reads tolerate transient inconsistency since the worst case is a
# missed "succeeded" status that's picked up on the next poll.
_jobs: dict[str, Job] = {}
_jobs_lock = asyncio.Lock()
_semaphore: asyncio.Semaphore  # initialised in lifespan


# ---------------------------------------------------------------------------
# Pydantic request body
# ---------------------------------------------------------------------------


class SimulateRequest(BaseModel):
    profile: str = Field(..., description="Full SimC profile text (.simc input).")
    fight_style: str = Field("Patchwerk", description="simc fight_style flag.")
    desired_targets: int = Field(1, ge=1, le=20)
    iterations: int = Field(5000, ge=100, le=50000)
    target_error: float | None = Field(None, ge=0.0, le=5.0)
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
            "consumable the profile doesn't already specify."
        ),
    )


# ---------------------------------------------------------------------------
# App lifespan — initialise the semaphore + the retention sweeper
# ---------------------------------------------------------------------------


from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    global _semaphore
    _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    sweeper = asyncio.create_task(_retention_sweeper(), name="retention_sweeper")
    try:
        yield
    finally:
        sweeper.cancel()
        # Cancel any still-running jobs so the sidecar shuts down cleanly.
        async with _jobs_lock:
            tasks = [j.task for j in _jobs.values() if j.task and not j.task.done()]
        for t in tasks:
            t.cancel()


app = FastAPI(title="simc-sidecar", lifespan=_lifespan)


async def _retention_sweeper() -> None:
    """Prune finished jobs older than ``JOB_RETENTION_S`` every 5 min."""
    try:
        while True:
            await asyncio.sleep(300)
            cutoff = time.time() - JOB_RETENTION_S
            async with _jobs_lock:
                to_drop = [
                    jid
                    for jid, j in _jobs.items()
                    if j.finished_at is not None and j.finished_at < cutoff
                ]
                for jid in to_drop:
                    _jobs.pop(jid, None)
            if to_drop:
                logger.info("retention sweep dropped %d job(s)", len(to_drop))
    except asyncio.CancelledError:
        pass


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    async with _jobs_lock:
        queued = sum(1 for j in _jobs.values() if j.status == "queued")
        running = sum(1 for j in _jobs.values() if j.status == "running")
    return {
        "ok": True,
        "simc_bin": SIMC_BIN,
        "exists": Path(SIMC_BIN).exists(),
        "queued": queued,
        "running": running,
        "max_concurrent": MAX_CONCURRENT,
    }


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


@app.post("/simulate", status_code=202)
async def submit_simulation(req: SimulateRequest) -> dict[str, Any]:
    """Queue a simulation. Returns 202 immediately with a job_id the
    caller polls on ``GET /jobs/{job_id}``."""
    if not Path(SIMC_BIN).exists():
        raise HTTPException(503, f"simc binary not found at {SIMC_BIN}")

    job_id = uuid.uuid4().hex
    job = Job(id=job_id, request=req.model_dump())
    async with _jobs_lock:
        _jobs[job_id] = job

    # The asyncio.Task replaces the per-request waiting model: the HTTP
    # handler returns immediately while the task runs in the background.
    job.task = asyncio.create_task(_execute_job(job_id, req), name=f"simc-job-{job_id}")
    return {"job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    async with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"job {job_id!r} not found (expired or unknown)")
    return _job_to_payload(job)


@app.get("/jobs")
async def list_jobs() -> dict[str, Any]:
    async with _jobs_lock:
        items = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return {"jobs": [_job_summary(j) for j in items]}


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str) -> dict[str, str]:
    async with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, f"job {job_id!r} not found")
        if job.status in ("succeeded", "failed", "cancelled"):
            return {"status": job.status}
        job.status = "cancelled"
        job.finished_at = time.time()
        if job.task and not job.task.done():
            job.task.cancel()
    return {"status": "cancelled"}


# ---------------------------------------------------------------------------
# Background execution
# ---------------------------------------------------------------------------


async def _execute_job(job_id: str, req: SimulateRequest) -> None:
    """Background task that acquires the concurrency semaphore, runs
    simc, and updates the in-memory job entry. Exceptions are caught
    and stored on the job so /jobs/{id} can report them — they never
    propagate up to the asyncio loop."""
    async with _semaphore:
        async with _jobs_lock:
            job = _jobs.get(job_id)
            if not job or job.status == "cancelled":
                return
            job.status = "running"
            job.started_at = time.time()
        try:
            result = await _run_simc(req)
            async with _jobs_lock:
                job = _jobs.get(job_id)
                if not job or job.status == "cancelled":
                    return
                job.status = "succeeded"
                job.result = result
                job.log_tail = result.pop("log_tail", "")
                job.finished_at = time.time()
        except asyncio.CancelledError:
            async with _jobs_lock:
                job = _jobs.get(job_id)
                if job and job.status not in ("succeeded", "failed"):
                    job.status = "cancelled"
                    job.finished_at = time.time()
            raise
        except HTTPException as exc:
            async with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job.status = "failed"
                    job.error = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                    job.finished_at = time.time()
        except Exception as exc:  # noqa: BLE001
            logger.exception("simc job %s failed", job_id)
            async with _jobs_lock:
                job = _jobs.get(job_id)
                if job:
                    job.status = "failed"
                    job.error = f"{type(exc).__name__}: {exc}"[:1000]
                    job.finished_at = time.time()


def _job_summary(job: Job) -> dict[str, Any]:
    return {
        "job_id": job.id,
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "fight_style": (job.request or {}).get("fight_style"),
        "iterations": (job.request or {}).get("iterations"),
        "rotation": (job.request or {}).get("rotation"),
    }


def _job_to_payload(job: Job) -> dict[str, Any]:
    payload = _job_summary(job)
    if job.result is not None:
        payload["result"] = job.result
    if job.error:
        payload["error"] = job.error
    if job.log_tail:
        payload["log_tail"] = job.log_tail
    return payload


# ---------------------------------------------------------------------------
# Core simc invocation (subprocess spawn + JSON parse)
# ---------------------------------------------------------------------------


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
    for line in profile.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.split("=", 1)[0].strip() == key:
            return True
    return False


_SPEC_RE = re.compile(r"^(\s*spec\s*=\s*\S+\s*)$", re.MULTILINE)


def _inject_dungeon_slice_flag(profile: str) -> str:
    """Insert ``enable_dungeon_slice=1`` right after the ``spec=…`` line.

    simc's DungeonSlice support is opt-in for some class modules
    (Demon Hunter, possibly others). The flag must live in the
    *player block* — putting it before the class line or as a CLI
    arg trips an "Unknown option" warning and is ignored. We splice
    it after ``spec=`` because every /simc paste has one and it's
    always inside the player block.
    """
    new, n = _SPEC_RE.subn(r"\1\nenable_dungeon_slice=1", profile, count=1)
    if n > 0:
        return new
    # No spec line — append at the end as a best-effort fallback.
    return profile.rstrip() + "\nenable_dungeon_slice=1\n"


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

    simc's JSON is verbose (hundreds of KiB per sim) — we keep only the
    DPS summary and per-ability damage breakdown. The frontend renders
    both directly.
    """
    sim = data.get("sim") or {}
    players = sim.get("players") or []
    if not players:
        raise ValueError("no players in simc output")
    player = players[0]
    collected = player.get("collected_data") or {}

    def _stat(field_: str, key: str = "mean") -> float:
        node = collected.get(field_) or {}
        return float(node.get(key, 0.0) or 0.0)

    dps_mean = _stat("dps") or fallback_dps_mean
    fight_length = _stat("fight_length")

    abilities: list[dict[str, Any]] = []
    for stats in player.get("stats") or []:
        if (stats.get("type") or "").lower() != "damage":
            continue
        actual = stats.get("actual_amount") or {}
        per_iter_damage = float(actual.get("mean", 0.0) or 0.0)
        if per_iter_damage <= 0:
            continue
        per_ability_dps = per_iter_damage / fight_length if fight_length else 0.0
        # simc emits ``id`` (Blizzard's spell ID — matches wowhead) and
        # ``spell_name`` (the localized English display name) on stats
        # entries. Auto-attacks have id=0/1 + empty spell_name (special-
        # cased on the frontend so we don't link them).
        spell_id = stats.get("id")
        try:
            spell_id_int = int(spell_id) if spell_id is not None else 0
        except (TypeError, ValueError):
            spell_id_int = 0
        abilities.append(
            {
                "name": stats.get("name") or "",
                "spell_id": spell_id_int,
                "spell_name": stats.get("spell_name") or "",
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

    version_node = data.get("version")
    if isinstance(version_node, dict):
        build = version_node.get("git_revision")
    elif isinstance(version_node, str):
        build = version_node
    else:
        build = None

    target_error_node = sim.get("target_error")
    target_error_actual = (
        target_error_node.get("dps") if isinstance(target_error_node, dict) else None
    )

    return {
        "dps_mean": dps_mean,
        "dps_min": _stat("dps", "min"),
        "dps_max": _stat("dps", "max"),
        "dps_stddev": _stat("dps", "std_dev"),
        "fight_length_mean": fight_length,
        "iterations": sim.get("iterations"),
        "target_error_actual": target_error_actual,
        "build_version": build or sim.get("build_version") or data.get("build_version"),
        "player_name": player.get("name"),
        "player_spec": player.get("specialization") or player.get("talent_tree"),
        "player_class": player.get("class"),
        "abilities": abilities,
    }


def _build_args_and_profile(
    req: SimulateRequest,
    *,
    inject_dungeon_slice: bool,
    rng_seed: int | None,
) -> tuple[str, list[str]]:
    """Compute the final profile text + extra CLI args for one attempt.

    Split out so the retry path can re-derive both with adjusted flags
    (``inject_dungeon_slice`` for the DH-style retry, ``rng_seed`` for
    the segfault-retry)."""
    profile_text = req.profile
    extra_args: list[str] = []
    if req.rotation == "blizzard":
        profile_text = _strip_action_lines(profile_text)
        extra_args.append("use_blizzard_action_list=1")
    elif req.rotation == "simc_default":
        profile_text = _strip_action_lines(profile_text)
    # custom → leave the profile alone

    fight_style_lc = req.fight_style.lower()
    if req.assume_raid_prep:
        profile_text = _inject_consumable_defaults(profile_text)
        if fight_style_lc in _RAID_PREP_FIGHT_STYLES:
            extra_args.extend(RAID_PREP_GLOBAL_FLAGS)

    if inject_dungeon_slice and fight_style_lc == "dungeonslice":
        profile_text = _inject_dungeon_slice_flag(profile_text)

    if rng_seed is not None:
        # ``deterministic`` pins simc's RNG to a known seed so the retry
        # can't repeat the same segfault path. The option name simc
        # accepts is ``seed=`` (not ``rng_seed=`` — that's "Unknown
        # option" and gets ignored).
        extra_args.append("deterministic=1")
        extra_args.append(f"seed={rng_seed}")

    return profile_text, extra_args


CRASH_DUMP_DIR = Path(os.environ.get("SIMC_CRASH_DUMP_DIR", "/tmp/simc-crashes"))


def _dump_crash(profile_text: str, args: list[str], out_text: str, err_text: str) -> str:
    """Persist the input.simc + args + stdout/stderr of a crashed run.

    Crashes that don't reproduce locally are usually item/thread-race
    bugs in a specific simc build. Keeping the exact failing input on
    disk lets us pull it later (via ``docker cp``) and bisect down to
    the offending item without having to ask the user to reproduce.
    """
    try:
        CRASH_DUMP_DIR.mkdir(parents=True, exist_ok=True)
        slug = uuid.uuid4().hex[:12]
        ts = time.strftime("%Y%m%d-%H%M%S")
        base = CRASH_DUMP_DIR / f"crash-{ts}-{slug}"
        base.with_suffix(".simc").write_text(profile_text, encoding="utf-8")
        base.with_suffix(".args").write_text(" ".join(args), encoding="utf-8")
        base.with_suffix(".log").write_text(
            f"=== stdout ===\n{out_text}\n\n=== stderr ===\n{err_text}\n",
            encoding="utf-8",
        )
        logger.warning("crash dump saved: %s.{simc,args,log}", base)
        return str(base)
    except Exception:  # noqa: BLE001
        logger.exception("could not save crash dump")
        return ""


async def _run_simc_once(
    req: SimulateRequest,
    *,
    profile_text: str,
    extra_args: list[str],
) -> tuple[int, str, str, dict | None, list[str]]:
    """Spawn simc once. Returns (exit_code, stdout, stderr, json_or_None, args).

    Does NOT raise — the caller decides what to do based on the exit
    code + stdout, so the retry helpers can introspect simc's output.
    Returns the full args list so the dump-on-crash path can persist
    the exact invocation that crashed."""
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
        data: dict | None = None
        if json_out.exists():
            try:
                with json_out.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except json.JSONDecodeError as exc:
                logger.warning("simc produced JSON we couldn't decode: %s", exc)
                data = None
        return proc.returncode or 0, out_text, err_text, data, args


async def _run_simc(req: SimulateRequest) -> dict[str, Any]:
    """Run simc with up to two narrowly-scoped retries:

    * **DungeonSlice gate**: a few specs (notably Demon Hunter) need
      ``enable_dungeon_slice=1`` to be spliced into the player block.
      We don't inject it up-front (it triggers an "Unknown option"
      warning for the majority of specs that auto-enable DungeonSlice),
      so on the first failure we look for simc's explicit
      "Dungeon Slice is disabled" hint and retry with the flag.

    * **Segfault**: simc 1205-01 has a sporadic crash bug for specific
      seed/item combinations. The same profile re-rolled with a fresh
      RNG seed usually goes through. Retry once with a random seed
      before giving up.
    """
    fight_style_lc = req.fight_style.lower()

    profile_text, extra_args = _build_args_and_profile(
        req, inject_dungeon_slice=False, rng_seed=None
    )
    logger.info(
        "simc spawn: fight=%s targets=%s iter=%s rotation=%s",
        req.fight_style,
        req.desired_targets,
        req.iterations,
        req.rotation,
    )
    rc, out_text, err_text, data, last_args = await _run_simc_once(
        req, profile_text=profile_text, extra_args=extra_args
    )
    last_profile = profile_text

    # Retry #1: explicit "Dungeon Slice is disabled" gate.
    if (
        data is None
        and fight_style_lc == "dungeonslice"
        and "Dungeon Slice is disabled" in (out_text + err_text)
    ):
        logger.info("simc reports DungeonSlice opt-in needed — retrying with flag")
        profile_text, extra_args = _build_args_and_profile(
            req, inject_dungeon_slice=True, rng_seed=None
        )
        rc, out_text, err_text, data, last_args = await _run_simc_once(
            req, profile_text=profile_text, extra_args=extra_args
        )
        last_profile = profile_text

    # Retry #2: segfault. simc's signal handler dumps
    # "sim_signal_handler: Segmentation fault!" and exits non-zero.
    # Re-roll with a fixed seed so the crashed thread-init path isn't
    # repeated. If the crash is item-deterministic this won't help —
    # which is what _dump_crash exists for.
    seg_hint = "Segmentation fault" in (out_text + err_text)
    if (rc in (11, -11) or seg_hint) and data is None:
        new_seed = random.getrandbits(63)
        logger.warning(
            "simc segfaulted (exit=%s) — retrying once with seed=%s",
            rc,
            new_seed,
        )
        profile_text, extra_args = _build_args_and_profile(
            req,
            inject_dungeon_slice=(fight_style_lc == "dungeonslice"
                                  and "Dungeon Slice is disabled" in (out_text + err_text)),
            rng_seed=new_seed,
        )
        rc, out_text, err_text, data, last_args = await _run_simc_once(
            req, profile_text=profile_text, extra_args=extra_args
        )
        last_profile = profile_text

    if rc != 0 and data is None:
        dump = _dump_crash(last_profile, last_args, out_text, err_text)
        suffix = f" (crash dump: {dump})" if dump else ""
        raise HTTPException(
            400,
            f"simc exit {rc}: {(err_text or out_text)[-1500:]}{suffix}",
        )
    if data is None:
        dump = _dump_crash(last_profile, last_args, out_text, err_text)
        suffix = f" (crash dump: {dump})" if dump else ""
        raise HTTPException(500, f"simc finished but produced no JSON{suffix}: {out_text[-800:]}")

    try:
        parsed = _parse_result(data)
    except ValueError as exc:
        raise HTTPException(500, f"could not parse simc JSON: {exc}")

    parsed["log_tail"] = out_text[-2000:]
    return parsed


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090, log_level="info")
