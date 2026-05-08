# Setup guide

## 1. Prerequisites

- Docker + Docker Compose v2
- A Warcraft Logs API v2 client (see [WCL_API_SETUP.md](WCL_API_SETUP.md))
- An Anthropic API key (https://console.anthropic.com)
- A working SMTP server (the app supports unauthenticated local relays out of the box)

## 2. Configuration

```powershell
cp .env.example .env
# Edit .env. At minimum:
#  - SECRET_KEY (long random string)
#  - WCL_CLIENT_ID + WCL_CLIENT_SECRET
#  - ANTHROPIC_API_KEY
#  - SMTP_HOST / SMTP_PORT / SMTP_FROM_EMAIL
#  - INITIAL_ADMIN_EMAIL + INITIAL_ADMIN_PASSWORD
#  - POSTGRES_PASSWORD
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
optional `local-ai` service running [Ollama](https://ollama.com) — it speaks
the OpenAI chat-completions API, so the backend talks to it the same way it
would talk to OpenAI cloud. The service only starts when you opt-in via a
Compose profile.

Requirements:

- An NVIDIA GPU + the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
  on the host (`nvidia-smi` must work).
- Enough VRAM for your chosen quantisation. For the default model
  `hf.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4_K_M`
  (≈ 21 GB on disk, fits on a 32 GB card with comfortable headroom for the
  KV cache).

Configure in `.env`:

```env
AI_PROVIDER=local
LOCAL_AI_BASE_URL=http://local-ai:11434/v1
LOCAL_AI_MODEL=hf.co/HauhauCS/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive:Q4_K_M
LOCAL_AI_API_KEY=dummy
```

Start the full stack including Ollama:

```powershell
docker compose --profile local-ai up -d --build
```

The first start of the `local-ai` container does **two** slow things:

1. Builds the small wrapper image (`./local-ai/Dockerfile`) — seconds.
2. The entrypoint runs `ollama pull <LOCAL_AI_MODEL>` once. For Q4_K_M of
   the default model that's ≈ 21 GB; expect 5-30 minutes depending on
   bandwidth. The download is cached in the `ollama-data` Docker volume, so
   subsequent restarts are instant.

Watch the load:

```powershell
docker compose logs -f local-ai
```

You'll see lines like `[local-ai] pulling …`, then `pull complete`, and
finally Ollama's own `Listening on [::]:11434`. The container's healthcheck
flips to healthy when `ollama list` succeeds — that means the API is up and
the model is registered locally.

Smoke test from the backend container:

```powershell
docker compose exec backend curl -s http://local-ai:11434/api/tags
docker compose exec backend curl -s http://local-ai:11434/v1/models
```

Both should list your model. If they do, run an analysis from the UI as
normal — the backend's OpenAI-compatible provider talks to Ollama through
the OpenAI SDK and the rest of the app is unchanged.

### Picking a different quantisation

The chosen HF repo offers several. Heavier = better quality, more VRAM:

| Tag       | Size    | Comment                               |
|-----------|---------|---------------------------------------|
| `IQ3_M`   | ~15 GB  | tightest fit, noticeable quality drop |
| `Q4_K_M`  | ~21 GB  | **default**, sweet spot for 24-32 GB  |
| `Q5_K_P`  | ~28 GB  | better quality, hugs 32 GB            |
| `Q6_K_P`  | ~31 GB  | only with > 32 GB or no other models  |
| `Q8_K_P`  | ~44 GB  | needs 48 GB+                          |

Switch by changing the `:Q4_K_M` suffix on `LOCAL_AI_MODEL` and restarting:

```powershell
docker compose --profile local-ai up -d local-ai
```

The new tag will be pulled on next start; the old one stays in the cache.

### Switching back to cloud

```powershell
# .env: AI_PROVIDER=anthropic    (or =openai)
docker compose stop local-ai
docker compose up -d backend
```

Existing analyses use the new provider for the next request — no code change.

### Troubleshooting local-ai

- **`ollama pull` fails with "no such manifest"** → wrong model tag. Run
  `docker compose exec local-ai ollama pull <tag>` manually with a tag from
  the HF repo's file list.
- **GPU not detected** → run `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`.
  If that fails, the NVIDIA Container Toolkit isn't installed on the host.
- **Model loads on CPU instead of GPU** → check `docker compose logs local-ai`
  for a `gpu disabled` line. Usually means the toolkit + driver versions don't
  match. Update both.
- **OOM during inference** → pick a smaller quant (e.g. drop from Q4_K_M to
  IQ4_XS), or set `OLLAMA_NUM_PARALLEL=1` (default). To cap context length
  per request, set the analyzer's `AI_MAX_TOKENS` lower in `.env`.
- **First analysis is slow** → the model gets loaded into VRAM lazily on the
  first request. Subsequent requests within `OLLAMA_KEEP_ALIVE` reuse the
  loaded weights.

## 9. Troubleshooting

- `backend` keeps restarting → `docker compose logs backend`. The most common
  cause is an unset `SECRET_KEY` or unreachable database.
- Wowhead tooltips don't appear → ad blockers can block `wowhead_power.js`.
- Daily top-logs job didn't run → check `docker compose logs worker` and the
  `TOP_LOGS_CRON` value (UTC). Trigger manually from **Admin → Top logs** or
  via the CLI helper above.
- AI analysis returns plain text without findings → Anthropic occasionally
  responds without a JSON object. The analyzer stores the raw text in
  `summary` even then; ask the user to retry.
