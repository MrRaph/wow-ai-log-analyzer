"""Schemas for the admin System (docker-control) and local-ai endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ContainerOut(BaseModel):
    name: str
    service: str
    image: str
    status: str
    health: str | None
    started_at: str | None
    finished_at: str | None
    is_local_ai: bool


class SystemStatusOut(BaseModel):
    enabled: bool
    project: str
    containers: list[ContainerOut]


# --- Local-AI supervisor passthrough schemas --------------------------------


class LocalAiModelConfig(BaseModel):
    """User-editable model parameters. Mirrors supervisor.ModelConfigIn."""

    hf_repo: str = Field(..., min_length=1, max_length=200)
    hf_file: str = Field(..., min_length=1, max_length=200)
    alias: str = Field(..., min_length=1, max_length=200)
    ctx_size: int = Field(16384, ge=512, le=1_000_000)
    enable_thinking: bool = True


class LocalAiConfigPatch(BaseModel):
    """PATCH body for the admin local-ai config endpoint."""

    config: LocalAiModelConfig | None = None
    desired_running: bool | None = None


class LocalAiDownloadOut(BaseModel):
    filename: str
    bytes_done: int
    bytes_total: int | None
    percent: float | None
    started_at: float
    finished_at: float | None
    error: str | None


class LocalAiStatusOut(BaseModel):
    """Reachability flag + supervisor-reported state."""

    reachable: bool
    config: LocalAiModelConfig | None = None
    desired_running: bool = False
    child_running: bool = False
    child_healthy: bool = False
    current_model_filename: str | None = None
    download: LocalAiDownloadOut | None = None
    last_error: str | None = None


class LocalAiModelFile(BaseModel):
    filename: str
    size_bytes: int
    is_loaded: bool
