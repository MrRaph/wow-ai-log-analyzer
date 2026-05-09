"""Local-AI supervisor — manages a llama.cpp server child process and
exposes a small management API the backend uses to drive it.

Layout inside the container:
  PID 1  → this Python process, listens on :8081 (management API)
  child  → ``llama-server`` spawned by us, listens on :8080 (inference API)

The backend talks to :8080 for inference (unchanged ``LOCAL_AI_BASE_URL``)
and to :8081 for management. This means we do NOT need Docker socket
access on the backend to switch models, list cached files or stop
inference when the admin disables local AI.

State persistence: ``/cache/supervisor-state.json`` (alongside cached
GGUFs). On boot we restore the last desired config; if none is saved we
seed from the LOCAL_AI_* env vars so a fresh install matches the
compose file's defaults.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException
from huggingface_hub import HfApi, hf_hub_download
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CACHE_DIR = Path(os.environ.get("LLAMA_CACHE", "/cache"))
STATE_FILE = CACHE_DIR / "supervisor-state.json"
INFERENCE_PORT = int(os.environ.get("LOCAL_AI_INFERENCE_PORT", "8080"))
SUPERVISOR_PORT = int(os.environ.get("LOCAL_AI_SUPERVISOR_PORT", "8081"))
LLAMA_BIN = os.environ.get("LLAMA_SERVER_BIN", "/app/llama-server")
HEALTH_TIMEOUT_S = 10.0

logger = logging.getLogger("supervisor")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class ModelConfig:
    """Settings for a single llama-server invocation.

    ``hf_repo`` + ``hf_file`` identify the GGUF to download from Hugging
    Face. ``alias`` is the model name returned by ``/v1/models`` (and
    must match the OpenAI SDK's ``model=`` parameter on the backend
    side). ``ctx_size`` is the KV cache context window in tokens.
    ``enable_thinking`` toggles Qwen-style chain-of-thought (off → much
    faster, on → noticeably better coaching findings).
    """

    hf_repo: str
    hf_file: str
    alias: str
    ctx_size: int = 16384
    enable_thinking: bool = True


@dataclass
class DownloadProgress:
    filename: str
    bytes_done: int = 0
    bytes_total: int | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    error: str | None = None

    @property
    def percent(self) -> float | None:
        if not self.bytes_total:
            return None
        return min(100.0, 100.0 * self.bytes_done / self.bytes_total)


def _env_default_config() -> ModelConfig | None:
    repo = os.environ.get("LOCAL_AI_HF_REPO")
    fname = os.environ.get("LOCAL_AI_HF_FILE")
    if not repo or not fname:
        return None
    return ModelConfig(
        hf_repo=repo,
        hf_file=fname,
        alias=os.environ.get("LOCAL_AI_MODEL", "local-llm"),
        ctx_size=int(os.environ.get("LOCAL_AI_CTX_SIZE", "16384") or 16384),
        enable_thinking=os.environ.get("LOCAL_AI_ENABLE_THINKING", "true").lower()
        in {"1", "true", "yes", "on"},
    )


@dataclass
class State:
    """In-memory state of the supervisor."""

    config: ModelConfig | None = None
    desired_running: bool = True
    download: DownloadProgress | None = None
    last_error: str | None = None
    # The currently spawned child Popen (in-memory only — never persisted).
    proc: subprocess.Popen | None = None
    # Path to the GGUF the live child was started with (so we can refuse
    # to delete a file that's currently mmap'd).
    proc_model_path: Path | None = None

    def to_persisted_json(self) -> dict:
        return {
            "config": asdict(self.config) if self.config else None,
            "desired_running": self.desired_running,
        }


def load_state() -> State:
    """Load saved state, falling back to env defaults on first boot."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text())
            cfg = data.get("config")
            return State(
                config=ModelConfig(**cfg) if cfg else _env_default_config(),
                desired_running=bool(data.get("desired_running", True)),
            )
        except Exception:
            logger.exception("Failed to load %s — falling back to env defaults", STATE_FILE)
    return State(config=_env_default_config(), desired_running=True)


def save_state(state: State) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state.to_persisted_json(), indent=2))
    tmp.replace(STATE_FILE)


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------


def _gguf_path(filename: str) -> Path:
    """Where we store a GGUF locally — flat layout under /cache."""
    return CACHE_DIR / filename


def _download_with_progress(state: State, cfg: ModelConfig) -> Path:
    """Synchronously download a GGUF, updating ``state.download`` as we go.

    Uses huggingface_hub which:
      - resolves repo metadata (so we can know bytes_total up front),
      - resumes partial downloads,
      - verifies SHA256,
      - dedupes identical files via content-addressable storage.
    """
    target = _gguf_path(cfg.hf_file)
    if target.exists() and target.stat().st_size > 0:
        # Already downloaded — fast path.
        logger.info("Model %s already cached at %s", cfg.hf_file, target)
        return target

    api = HfApi()
    bytes_total: int | None = None
    try:
        # Probe the repo for the file's size so the UI has a denominator.
        info = api.repo_info(cfg.hf_repo, files_metadata=True)
        for f in info.siblings or []:
            if f.rfilename == cfg.hf_file:
                bytes_total = f.size
                break
    except Exception:
        logger.exception("Could not pre-fetch size of %s/%s", cfg.hf_repo, cfg.hf_file)

    state.download = DownloadProgress(filename=cfg.hf_file, bytes_total=bytes_total)
    logger.info("Downloading %s/%s (~%s bytes)", cfg.hf_repo, cfg.hf_file, bytes_total)

    # huggingface_hub uses tqdm internally; the cleanest way to track
    # progress without monkey-patching is to download to the HF cache
    # then copy/symlink, while a poller thread watches the partial file
    # size on disk. The HF cache resolver returns the final file path.
    download_done = threading.Event()

    def _poll_progress(target_dir: Path) -> None:
        """Watch the cache directory for any *.incomplete file growing."""
        while not download_done.is_set():
            try:
                # huggingface_hub places partial downloads as
                # <name>.incomplete in its blob cache.
                for p in target_dir.rglob("*.incomplete"):
                    sz = p.stat().st_size
                    if state.download:
                        state.download.bytes_done = sz
            except FileNotFoundError:
                pass
            time.sleep(2.0)

    hf_cache = CACHE_DIR / ".hf"
    poll_thread = threading.Thread(target=_poll_progress, args=(hf_cache,), daemon=True)
    poll_thread.start()
    try:
        cached = hf_hub_download(
            repo_id=cfg.hf_repo,
            filename=cfg.hf_file,
            cache_dir=str(hf_cache),
        )
    except Exception as exc:
        if state.download:
            state.download.error = str(exc)
            state.download.finished_at = time.time()
        raise
    finally:
        download_done.set()

    # Materialise a flat /cache/<filename> path so the model list (and
    # llama-server) doesn't have to traverse HF's blob layout. We
    # hard-link if possible (same filesystem) to avoid doubling disk
    # use, falling back to copy.
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if target.exists():
            target.unlink()
        os.link(cached, target)
    except OSError:
        shutil.copyfile(cached, target)

    if state.download:
        state.download.bytes_done = target.stat().st_size
        if state.download.bytes_total is None:
            state.download.bytes_total = state.download.bytes_done
        state.download.finished_at = time.time()
    logger.info("Download complete: %s", target)
    return target


# ---------------------------------------------------------------------------
# llama-server child management
# ---------------------------------------------------------------------------


def _build_llama_args(cfg: ModelConfig, model_path: Path) -> list[str]:
    args = [
        LLAMA_BIN,
        "--host", "0.0.0.0",
        "--port", str(INFERENCE_PORT),
        "--model", str(model_path),
        "--alias", cfg.alias,
        "--n-gpu-layers", "999",
        "--ctx-size", str(cfg.ctx_size),
        "--jinja",
    ]
    if not cfg.enable_thinking:
        # Qwen-3.x ships a chat template that toggles a /think tag based
        # on a jinja variable; we expose this as ``enable_thinking=false``
        # via the upstream ``--chat-template-kwargs`` flag.
        args += ["--chat-template-kwargs", json.dumps({"enable_thinking": False})]
    return args


def _stop_child(state: State, *, timeout: float = 30.0) -> None:
    if state.proc is None:
        return
    if state.proc.poll() is not None:
        state.proc = None
        state.proc_model_path = None
        return
    logger.info("Stopping llama-server (pid=%s)", state.proc.pid)
    try:
        state.proc.terminate()
        state.proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("llama-server didn't terminate in %ss — killing", timeout)
        state.proc.kill()
        state.proc.wait()
    finally:
        state.proc = None
        state.proc_model_path = None


def _start_child(state: State) -> None:
    if state.config is None:
        raise RuntimeError("No model configured — set config first.")
    if state.proc and state.proc.poll() is None:
        logger.info("llama-server already running (pid=%s)", state.proc.pid)
        return

    cfg = state.config
    model_path = _gguf_path(cfg.hf_file)
    if not model_path.exists():
        # Block on download — caller should run this in a worker thread.
        model_path = _download_with_progress(state, cfg)

    args = _build_llama_args(cfg, model_path)
    logger.info("Spawning llama-server: %s", " ".join(args))
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        env=os.environ.copy(),
    )
    state.proc = proc
    state.proc_model_path = model_path
    state.last_error = None


def _child_is_healthy(state: State) -> bool:
    if state.proc is None or state.proc.poll() is not None:
        return False
    try:
        with httpx.Client(timeout=2.0) as c:
            r = c.get(f"http://127.0.0.1:{INFERENCE_PORT}/health")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


# ---------------------------------------------------------------------------
# Worker thread — long-running operations off the event loop
# ---------------------------------------------------------------------------

# We funnel start/stop/download through a single worker thread so the
# event loop never blocks and we never have two concurrent ``llama-server``
# spawn attempts racing.
_op_lock = threading.Lock()


def _do_apply_async(state: State) -> None:
    """Apply ``state.desired_running`` and ``state.config`` to the child."""
    with _op_lock:
        try:
            if not state.desired_running:
                _stop_child(state)
                return
            cfg = state.config
            if cfg is None:
                _stop_child(state)
                return
            target_path = _gguf_path(cfg.hf_file)
            running = state.proc is not None and state.proc.poll() is None
            same_model = running and state.proc_model_path == target_path
            if running and same_model:
                # Nothing to do — config matches what's already running.
                return
            _stop_child(state)
            _start_child(state)
        except Exception as exc:
            logger.exception("apply failed")
            state.last_error = str(exc)


def schedule_apply(state: State) -> None:
    """Kick off ``_do_apply_async`` in a daemon thread."""
    t = threading.Thread(target=_do_apply_async, args=(state,), daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class ModelConfigIn(BaseModel):
    hf_repo: str = Field(..., min_length=1, max_length=200)
    hf_file: str = Field(..., min_length=1, max_length=200)
    alias: str = Field(..., min_length=1, max_length=200)
    ctx_size: int = Field(16384, ge=512, le=1_000_000)
    enable_thinking: bool = True


class ConfigPatch(BaseModel):
    config: ModelConfigIn | None = None
    desired_running: bool | None = None


class DownloadOut(BaseModel):
    filename: str
    bytes_done: int
    bytes_total: int | None
    percent: float | None
    started_at: float
    finished_at: float | None
    error: str | None


class StatusOut(BaseModel):
    config: ModelConfigIn | None
    desired_running: bool
    child_running: bool
    child_healthy: bool
    current_model_filename: str | None
    download: DownloadOut | None
    last_error: str | None


class ModelFileOut(BaseModel):
    filename: str
    size_bytes: int
    is_loaded: bool


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

STATE = load_state()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if STATE.desired_running and STATE.config:
        # Boot the child in the background so /healthz responds quickly
        # even when the model still has to download.
        schedule_apply(STATE)
    try:
        yield
    finally:
        with _op_lock:
            _stop_child(STATE)


app = FastAPI(title="local-ai supervisor", lifespan=lifespan)


def _download_to_out(d: DownloadProgress | None) -> DownloadOut | None:
    if d is None:
        return None
    return DownloadOut(
        filename=d.filename,
        bytes_done=d.bytes_done,
        bytes_total=d.bytes_total,
        percent=d.percent,
        started_at=d.started_at,
        finished_at=d.finished_at,
        error=d.error,
    )


def _config_to_out(c: ModelConfig | None) -> ModelConfigIn | None:
    if c is None:
        return None
    return ModelConfigIn(**asdict(c))


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/api/v1/status", response_model=StatusOut)
def get_status() -> StatusOut:
    running = STATE.proc is not None and STATE.proc.poll() is None
    return StatusOut(
        config=_config_to_out(STATE.config),
        desired_running=STATE.desired_running,
        child_running=running,
        child_healthy=_child_is_healthy(STATE) if running else False,
        current_model_filename=(
            STATE.proc_model_path.name if STATE.proc_model_path else None
        ),
        download=_download_to_out(STATE.download),
        last_error=STATE.last_error,
    )


@app.patch("/api/v1/config", response_model=StatusOut)
def patch_config(patch: ConfigPatch) -> StatusOut:
    if patch.config is not None:
        STATE.config = ModelConfig(**patch.config.model_dump())
    if patch.desired_running is not None:
        STATE.desired_running = patch.desired_running
    save_state(STATE)
    schedule_apply(STATE)
    return get_status()


@app.post("/api/v1/start", response_model=StatusOut)
def start_inference() -> StatusOut:
    STATE.desired_running = True
    save_state(STATE)
    schedule_apply(STATE)
    return get_status()


@app.post("/api/v1/stop", response_model=StatusOut)
def stop_inference() -> StatusOut:
    STATE.desired_running = False
    save_state(STATE)
    schedule_apply(STATE)
    return get_status()


@app.get("/api/v1/models", response_model=list[ModelFileOut])
def list_models() -> list[ModelFileOut]:
    if not CACHE_DIR.exists():
        return []
    out: list[ModelFileOut] = []
    loaded = STATE.proc_model_path
    for p in sorted(CACHE_DIR.glob("*.gguf")):
        out.append(
            ModelFileOut(
                filename=p.name,
                size_bytes=p.stat().st_size,
                is_loaded=(loaded is not None and p == loaded),
            )
        )
    return out


@app.delete("/api/v1/models/{filename}")
def delete_model(filename: str) -> dict:
    # Refuse path traversal — only files directly inside CACHE_DIR.
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="invalid filename")
    target = _gguf_path(filename)
    if not target.exists():
        raise HTTPException(status_code=404, detail="not found")
    if STATE.proc_model_path == target and STATE.proc and STATE.proc.poll() is None:
        raise HTTPException(
            status_code=409,
            detail="model is currently loaded — stop inference first",
        )
    target.unlink()
    # Also try to free the HF cache copy if we hard-linked.
    return {"deleted": filename}


def _install_signal_handlers() -> None:
    def _term(_signum, _frame):
        logger.info("received SIGTERM/SIGINT — stopping child")
        with _op_lock:
            _stop_child(STATE)
        os._exit(0)

    signal.signal(signal.SIGTERM, _term)
    signal.signal(signal.SIGINT, _term)


def main() -> None:
    import uvicorn

    _install_signal_handlers()
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=SUPERVISOR_PORT,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
