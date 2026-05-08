# Setup guide

## 1. Prerequisites

- Docker + Docker Compose v2
- A Warcraft Logs API v2 client (see [WCL_API_SETUP.md](WCL_API_SETUP.md))
- **One of**:
  - an NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
    on the host (default — runs the AI locally for free), **or**
  - an Anthropic API key (https://console.anthropic.com), **or**
  - any OpenAI-compatible API key
- A working SMTP server (the app supports unauthenticated local relays out of the box)

## 2. Configuration

```powershell
cp .env.example .env
# Edit .env. At minimum:
#  - SECRET_KEY (long random string)
#  - WCL_CLIENT_ID + WCL_CLIENT_SECRET
#  - SMTP_HOST / SMTP_PORT / SMTP_FROM_EMAIL
#  - INITIAL_ADMIN_EMAIL + INITIAL_ADMIN_PASSWORD
#  - POSTGRES_PASSWORD
#  - AI_PROVIDER (default: "local"; set ANTHROPIC_API_KEY if "anthropic")
#  - NEXT_PUBLIC_IMPRINT_* (your address — required for the public Imprint
#    page under German § 5 DDG; otherwise the page renders [Platzhalter])
#  - CORS_ALLOW_ORIGINS — add http://<your-LAN-IP>:3000 if you intend to
#    reach the app from another device on your network
```

## 3. Build & launch

```powershell
docker compose up -d --build
docker compose logs -f backend
```

The backend will run Alembic migrations automatically on startup, then create
the initial admin if no admin exists. Once you see `Application startup
complete.`, open http://localhost:3000.

## 4. First login

1. Sign in with `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`.
2. Visit **Admin → Settings** and:
   - Confirm or disable open registration.
   - Send invitations to your friends.
3. Visit **Admin → Settings → AI** and adjust the model (`claude-sonnet-4-6` or
   `claude-opus-4-7`). Sonnet is the default.

## 5. Updating

```powershell
git pull
docker compose pull
docker compose up -d --build
```

Migrations run automatically on every backend boot.

## 6. Backups

The Postgres volume `postgres-data` is the source of truth. Use `pg_dump`
inside the `db` container:

```powershell
docker compose exec db pg_dump -U $env:POSTGRES_USER $env:POSTGRES_DB > backup.sql
```

## 7. Seeding top-logs for a new tier

The weekly worker only refreshes (spec, encounter) pairs that already exist in
the cache. To add a new encounter (e.g. when a new raid tier launches):

```powershell
docker compose exec backend uv run python -m scripts.seed_top_logs <ENCOUNTER_ID>
# Mythic+ dungeon boss (skips raid-difficulty filter):
docker compose exec backend uv run python -m scripts.seed_top_logs --m-plus <ENCOUNTER_ID>
```

`ENCOUNTER_ID` is the stable numeric ID Warcraft Logs uses internally — copy
it from the URL of the encounter page on https://www.warcraftlogs.com/zones/
(`?boss=<ID>`).

Once seeded, the weekly cron job (`TOP_LOGS_CRON`, default Wednesday 08:00 UTC
to align with the EU reset) will keep it fresh automatically.

## 8. Using a local LLM instead of cloud Anthropic / OpenAI

You can run the whole AI stack on your own GPU. The compose file ships an
optional `local-ai` service running the official
[`ggml-org/llama.cpp:server-cuda`](https://github.com/ggml-org/llama.cpp)
image — it speaks the OpenAI chat-completions API, so the backend talks to
it the same way it would talk to OpenAI cloud. The service only starts when
you opt in via a Compose profile.

> We use llama.cpp's official server image rather than Ollama because Ollama
> bundles a forked llama.cpp that lags behind upstream — bleeding-edge model
> architectures (e.g. `qwen35moe`) only work with the official upstream build.

Requirements:

- An NVIDIA GPU + the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
  on the host (`nvidia-smi` must work).
- Enough VRAM for your chosen quantisation. The default `Q4_K_M` is ≈ 21 GB
  on disk and fits comfortably on a 32 GB card together with a 64k KV cache.
- **RTX 50-series (Blackwell, sm_120) note:** the bundled image works against
  any modern PyTorch host, but if you also use the Forge / WebUI auxiliary
  scripts in this repo, ensure your local PyTorch is ≥ 2.7 with CUDA 12.8 —
  earlier builds don't ship Blackwell kernels.

Configure in `.env`:

```env
AI_PROVIDER=local
LOCAL_AI_BASE_URL=http://local-ai:8080/v1
LOCAL_AI_HF_REPO=HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive
LOCAL_AI_HF_FILE=Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf
LOCAL_AI_MODEL=qwen3.6-35b-a3b-q4_k_m
LOCAL_AI_API_KEY=dummy
LOCAL_AI_ENABLE_THINKING=true
LOCAL_AI_CTX_SIZE=65536
# If you have a HF auth token (rare for public repos): HUGGINGFACE_TOKEN=...
```

Start the full stack including the local-AI container:

```powershell
docker compose --profile local-ai up -d --build
```

The first start downloads the GGUF directly from Hugging Face into the
`llama-cache` Docker volume and loads it into VRAM. For Q4_K_M of the
default model that's ≈ 21 GB; expect 5-30 minutes depending on bandwidth.
Subsequent restarts are instant.

Watch the load:

```powershell
docker compose logs -f local-ai
```

You'll see HTTP download lines, then llama.cpp's own model-load output, and
finally `server is listening on http://0.0.0.0:8080`. The healthcheck flips
to healthy once `/v1/models` returns 200.

Smoke test from the backend container:

```powershell
docker compose exec backend curl -s http://local-ai:8080/v1/models
```

If it lists your model, run an analysis from the UI — the backend's
OpenAI-compatible provider talks to llama.cpp via the OpenAI SDK and the
rest of the app is unchanged.

### Picking a different quantisation

The chosen HF repo offers several files. Heavier = better quality, more VRAM:

| Tag       | Size    | Comment                               |
|-----------|---------|---------------------------------------|
| `IQ3_M`   | ~15 GB  | tightest fit, noticeable quality drop |
| `Q4_K_M`  | ~21 GB  | **default**, sweet spot for 24-32 GB  |
| `Q5_K_P`  | ~28 GB  | better quality, hugs 32 GB            |
| `Q6_K_P`  | ~31 GB  | only with > 32 GB or no other models  |
| `Q8_K_P`  | ~44 GB  | needs 48 GB+                          |

Switch by editing `LOCAL_AI_HF_FILE` (and matching `LOCAL_AI_MODEL` alias)
and restarting:

```powershell
docker compose --profile local-ai up -d local-ai
```

The new file is downloaded on next start; the old one stays in the cache.

### Switching back to cloud

```powershell
# .env: AI_PROVIDER=anthropic    (or =openai)
docker compose stop local-ai
docker compose up -d backend
```

Existing analyses use the new provider for the next request — no code change.

### Troubleshooting local-ai

- **`hf-pull` fails / "no such file"** → wrong `LOCAL_AI_HF_REPO` or
  `LOCAL_AI_HF_FILE`. Verify both against the file list on Hugging Face.
- **GPU not detected** → run `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`.
  If that fails, the NVIDIA Container Toolkit isn't installed on the host.
- **`no usable GPU found`** in llama.cpp logs → the CUDA shared libraries
  aren't on the loader path. The compose file already sets
  `LD_LIBRARY_PATH=/app:/usr/local/cuda/lib64` for this; if you customised
  the service, keep that env var.
- **OOM during inference** → pick a smaller quant or lower `LOCAL_AI_CTX_SIZE`
  (e.g. 32768 instead of 65536). `AI_MAX_TOKENS` caps the response length.
- **First analysis is slow** → llama.cpp keeps the model in VRAM; the very
  first request after cold-start incurs model load + KV-cache prefill.

## 9. Imprint + Privacy Policy

The frontend exposes `/legal/imprint` and `/legal/privacy` reachable without
login (linked in the footer). The Privacy Policy is DSGVO/GDPR-conformant
and parameterised against the actual stack — no edits needed unless you add
new data processing.

The Imprint pulls its address fields from build-time env variables:

```env
NEXT_PUBLIC_IMPRINT_NAME=Daniel Schwarz
NEXT_PUBLIC_IMPRINT_STREET=Musterstraße 1
NEXT_PUBLIC_IMPRINT_POSTAL_CITY=12345 Musterstadt
NEXT_PUBLIC_IMPRINT_COUNTRY=Deutschland
NEXT_PUBLIC_IMPRINT_EMAIL=kontakt@your-domain.tld
NEXT_PUBLIC_IMPRINT_PHONE=        # optional, omit line if empty
```

Empty fields render as visible `[Platzhalter]` placeholders so missing data
is obvious. **`NEXT_PUBLIC_*` vars are baked into the JS bundle at build
time** — after changing them you must rebuild the frontend image:

```powershell
docker compose build frontend
docker compose up -d --force-recreate frontend
```

## 10. Troubleshooting

- `backend` keeps restarting → `docker compose logs backend`. The most common
  cause is an unset `SECRET_KEY` or unreachable database.
- Wowhead tooltips don't appear → ad blockers can block `wowhead_power.js`.
- Daily top-logs job didn't run → check `docker compose logs worker` and the
  `TOP_LOGS_CRON` value (UTC). Trigger manually from **Admin → Top logs** or
  via the CLI helper in §7.
- AI analysis returns plain text without findings → the model occasionally
  responds without a JSON object. The analyser stores the raw text in
  `summary` and marks the analysis `succeeded` anyway; ask the user to retry.
- CORS preflight returns 400 when accessing the app via LAN IP → add that
  origin (e.g. `http://192.168.1.20:3000`) to `CORS_ALLOW_ORIGINS` in `.env`
  and restart the backend.
