# Setup guide

## 1. Prerequisites

- Docker + Docker Compose v2
- A Warcraft Logs API v2 client (see [WCL_API_SETUP.md](WCL_API_SETUP.md))
- **One of** (or none — admins can leave AI disabled and let users
  bring their own keys via BYOK):
  - an NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
    on the host (default — runs the AI locally for free), **or**
  - an Anthropic API key (https://console.anthropic.com), **or**
  - an OpenAI / Azure-OpenAI / OpenAI-compatible API key
- A working SMTP server (the app supports unauthenticated local relays out of the box)

## 2. Configuration

```powershell
cp .env.example .env
# Edit .env. At minimum:
#  - SECRET_KEY (long random string ≥32 chars; openssl rand -hex 64)
#  - WCL_CLIENT_ID + WCL_CLIENT_SECRET
#  - SMTP_HOST / SMTP_PORT / SMTP_FROM_EMAIL
#  - INITIAL_ADMIN_EMAIL + INITIAL_ADMIN_PASSWORD
#  - POSTGRES_PASSWORD
#  - AI_PROVIDER (default: "anthropic"; set ANTHROPIC_API_KEY accordingly,
#    or switch to "openai" / "local" / "disabled")
#  - IMPRINT_* (your address — required for the public Imprint page
#    under German § 5 DDG; otherwise the page renders [Platzhalter])
#  - CORS_ALLOW_ORIGINS — add http://<your-LAN-IP>:3000 if you reach the
#    app from another device on your network without a reverse proxy
```

### Reverse-proxy expectation (production)

The frontend uses **same-origin URLs** (`/api/v1/...`) for all backend
calls — no `NEXT_PUBLIC_API_BASE_URL` baked into the bundle. In
production you put an HTTPS reverse proxy (Caddy / nginx / Traefik) in
front and route by path:

| Path prefix | Forward to                |
|-------------|---------------------------|
| `/api/*`    | `127.0.0.1:8000` (backend)|
| `/*`        | `127.0.0.1:3000` (frontend)|

For local `npm run dev` outside docker, Next.js's dev server proxies
`/api/*` to `http://localhost:8000` automatically (see
`frontend/next.config.ts`). Override with `DEV_API_PROXY=...` if your
backend runs elsewhere.

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
3. Pick the **AI provider**:
   - `Local (llama.cpp)` — runs on your own GPU. See §8 for the one-time
     setup; afterwards the active model can be switched live in the UI.
   - `Anthropic Claude` — pick `claude-sonnet-4-6`, `claude-opus-4-7`, or
     `claude-haiku-4-5`. Requires `ANTHROPIC_API_KEY` in `.env`.
   - `OpenAI` — `gpt-4o`, `gpt-4o-mini`, or `o1-preview`. Requires
     `OPENAI_API_KEY` (and optionally `OPENAI_BASE_URL` for Azure).
   - `Disabled` — app-wide AI is off. Users can still analyse their own
     logs by adding a personal API key under **Profile → Bring-your-own
     AI provider** (BYOK). Keys are stored Fernet-encrypted in Postgres.

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

The weekly worker only refreshes (spec, encounter) pairs that already exist
in the cache. To add new encounters (e.g. when a new raid tier launches),
go to **Admin → Top-Logs Tools**:

- **Seed current tier** auto-discovers the live retail raid via WCL's
  `worldData.zones`, previews the encounter list it would queue, and on
  confirm fans out one per-encounter background job per spec. Each row
  shows live progress (rankings fetched, details fetched, ETA).
- **Seed single encounter** lets you queue just one encounter by numeric
  ID — useful for catching up an encounter you missed, or for Mythic+
  bosses where you toggle the "M+" switch (skips the raid-difficulty
  filter).

`ENCOUNTER_ID` is the stable numeric ID Warcraft Logs uses internally —
copy it from the URL of the encounter page on
https://www.warcraftlogs.com/zones/ (`?boss=<ID>`).

Once seeded, the weekly cron job (`TOP_LOGS_CRON`, default Wednesday
08:00 UTC to align with the EU reset) will keep it fresh and
automatically pick up newly-released current-tier encounters.

If you prefer the CLI for scripted runs, the underlying helper is still
available:

```powershell
docker compose exec backend uv run python -m scripts.seed_top_logs <ENCOUNTER_ID>
docker compose exec backend uv run python -m scripts.seed_top_logs --m-plus <ENCOUNTER_ID>
```

## 8. Using a local LLM instead of cloud Anthropic / OpenAI

You can run the whole AI stack on your own GPU. The compose file ships an
optional `local-ai` service that wraps the official
[`ggml-org/llama.cpp:server-cuda`](https://github.com/ggml-org/llama.cpp)
image with a small Python supervisor (`local-ai/supervisor.py`). The
supervisor:

- spawns `llama-server` as a child process and forwards the OpenAI-compatible
  inference API on port `8080` (unchanged for the backend);
- exposes a tiny management API on port `8081` the admin UI uses to switch
  models, watch download progress, list/delete cached GGUFs and stop or
  start inference — **all without docker socket access**;
- persists its config to `/cache/supervisor-state.json` so admin changes
  survive container restarts.

The service only starts when you opt in via a Compose profile.

> We use llama.cpp's official server image rather than Ollama because Ollama
> bundles a forked llama.cpp that lags behind upstream — bleeding-edge model
> architectures (e.g. `qwen35moe`) only work with the official upstream build.

Requirements:

- An NVIDIA GPU + the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
  on the host (`nvidia-smi` must work).
- Enough VRAM for your chosen quantisation. The default `Q4_K_M` is ≈ 21 GB
  on disk and fits comfortably on a 32 GB card together with a 64k KV cache.

Configure the **initial defaults** in `.env` (the supervisor seeds its
state from these on first boot — afterwards changes happen in the admin UI):

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

The container's healthcheck flips to healthy as soon as the supervisor
itself is up (port 8081) — that happens within seconds. The model
download / load runs in the background; you can watch live progress in
the admin UI's **Local AI model** card without waiting for it to finish.

```powershell
docker compose logs -f local-ai
```

Smoke test from the backend container once the model is loaded:

```powershell
docker compose exec backend curl -s http://local-ai:8080/v1/models
docker compose exec backend curl -s http://local-ai:8081/api/v1/status
```

### Managing the model from the admin UI

Once the supervisor is up, **Admin → Local AI model** lets you:

- Edit `hf_repo` / `hf_file` / `alias` / `ctx_size` / `enable_thinking` and
  apply — the supervisor downloads the new GGUF (live progress bar) and
  restarts `llama-server` automatically with the new args.
- Stop inference (frees VRAM) / Start it again. Useful when you want the
  local-ai container running but VRAM available for something else.
- See cached GGUFs and delete the ones you don't want anymore. The
  currently-loaded file is locked from deletion until you stop inference.

Switching the AI-provider drop-down at the top of the admin page also
calls into the supervisor: picking `Anthropic` / `OpenAI` / `Disabled`
stops the inference child (frees VRAM); picking `Local` again re-spawns it.
With `ADMIN_DOCKER_CONTROL=true` the whole container is stopped/started
in addition (saves the supervisor's own RAM footprint too).

### Picking a different quantisation

The chosen HF repo offers several files. Heavier = better quality, more VRAM:

| Tag       | Size    | Comment                               |
|-----------|---------|---------------------------------------|
| `IQ3_M`   | ~15 GB  | tightest fit, noticeable quality drop |
| `Q4_K_M`  | ~21 GB  | **default**, sweet spot for 24-32 GB  |
| `Q5_K_P`  | ~28 GB  | better quality, hugs 32 GB            |
| `Q6_K_P`  | ~31 GB  | only with > 32 GB or no other models  |
| `Q8_K_P`  | ~44 GB  | needs 48 GB+                          |

Switch by editing the **GGUF filename** (and matching alias) in the
admin Local-AI card and clicking *Apply config*. The new file downloads
into `/cache` and replaces the running model; the old GGUF stays in the
cache until you delete it.

### Switching back to cloud

Pick `Anthropic` or `OpenAI` from the **Admin → Settings → AI provider**
dropdown and save. The supervisor stops the inference child (VRAM freed
within a few seconds); existing analyses use the new provider on the next
request — no code change, no `.env` edit. With `ADMIN_DOCKER_CONTROL=true`
the local-ai container is also stopped automatically.

### Troubleshooting local-ai

- **Card shows "Local-AI container is not running"** → you started the
  stack without `--profile local-ai`. Re-run `docker compose --profile
  local-ai up -d`. The supervisor only listens once that profile is
  active.
- **Download fails / "no such file"** → wrong `hf_repo` or `hf_file`.
  Verify both against the file list on Hugging Face. The supervisor's
  `last_error` field on the Local-AI card shows the upstream error.
- **GPU not detected** → run `docker run --rm --gpus all
  nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`. If that fails, the
  NVIDIA Container Toolkit isn't installed on the host.
- **`no usable GPU found`** in llama.cpp logs → the CUDA shared libraries
  aren't on the loader path. The compose file already sets
  `LD_LIBRARY_PATH=/app:/usr/local/cuda/lib64` for this; if you customised
  the service, keep that env var.
- **OOM during inference** → pick a smaller quant in the admin card or
  lower the context size (e.g. 32768 instead of 65536). `AI_MAX_TOKENS`
  in `.env` caps the response length.
- **First analysis is slow** → llama.cpp keeps the model in VRAM; the very
  first request after cold-start incurs model load + KV-cache prefill.
- **Supervisor seems wedged** → `docker compose restart local-ai`.
  Persisted state is on the `llama-cache` volume, so no config is lost.

## 9. Imprint + Privacy Policy

The frontend exposes `/legal/imprint` and `/legal/privacy` reachable
without login (linked in the footer). The Privacy Policy is
DSGVO/GDPR-conformant and parameterised against the actual stack — no
edits needed unless you add new data processing.

The Imprint pulls its address fields from runtime env variables (server
component reads `process.env` per request):

```env
IMPRINT_NAME=Your Name
IMPRINT_STREET=Musterstraße 1
IMPRINT_POSTAL_CITY=12345 Musterstadt
IMPRINT_COUNTRY=Deutschland
IMPRINT_EMAIL=contact@your-domain.tld
IMPRINT_PHONE=        # optional, omit line if empty
```

Empty fields render as visible `[Platzhalter]` placeholders so missing
data is obvious. **No rebuild required** — change `.env` and restart
the frontend container:

```powershell
docker compose up -d --force-recreate frontend
```

## 10. Optional: Cloudflare Turnstile captcha

Protect login, register, forgot-password and accept-invite from automated
abuse. Both keys must be set; either being empty (or `TURNSTILE_ENABLED=false`)
disables the widget entirely.

1. Get a free key pair at
   <https://dash.cloudflare.com/?to=/:account/turnstile>. Add your hostname
   (e.g. `wow.your-domain.tld` and `localhost` for dev).
2. Fill `.env`:

   ```env
   TURNSTILE_ENABLED=true
   TURNSTILE_SECRET_KEY=<your secret key>
   NEXT_PUBLIC_TURNSTILE_SITE_KEY=<your site key>
   ```

3. Restart the affected services to pick up the new env vars:

   ```powershell
   docker compose up -d --force-recreate backend frontend
   ```

The site key reaches the browser through the `/api/v1/config` endpoint
(no rebuild needed), the secret key stays on the backend. The privacy
policy already documents Turnstile's data flow when enabled. The widget
renders locale-aware (`de` / `en`).

## 11. Optional: Admin Docker control (System card)

When `ADMIN_DOCKER_CONTROL=true`, the admin UI shows a **System** card
listing every container in this compose stack with restart / start / stop
buttons. The dropdown for `AI provider` also auto-toggles the whole
local-ai container (in addition to the supervisor child).

> **Security note.** This requires `/var/run/docker.sock` to be mounted
> into the backend container. That mount is **equivalent to root on the
> host** — anyone who gets a shell in the backend gets root on your
> machine. Only enable on single-tenant self-hosted instances where the
> admin is also the host operator. Leave it `false` on shared deployments.

The mount is declared in `docker-compose.yml` (under the `backend`
service's `volumes:` block, with a big SECURITY comment around it).
Toggling `ADMIN_DOCKER_CONTROL` has no effect until you recreate the
backend:

```powershell
docker compose up -d --force-recreate backend
```

When off, the System card is hidden and provider changes only act on the
supervisor (no whole-container start/stop). For full defence-in-depth on
deployments that will never use this feature, **comment the
`/var/run/docker.sock` mount lines out** in `docker-compose.yml` — even
a future RCE in the backend then has no path to host-root via Docker.

## 12. CI/CD via GitHub Actions

`.github/workflows/ci.yml` runs on every PR (tests only) and on every
push to `main` / `master` (tests + publish backend image to ghcr.io).

**On PRs:** backend `pytest`, frontend `tsc --noEmit` + `next lint`,
and a docker-compose syntax check.

**On main pushes:** the same tests, then parallel build + push of
both `backend` and `frontend` images to ghcr with:

- `:latest` — newest main commit
- `:sha-<short>` — immutable per-commit reference

**On semver tags (`v0.2.0`):** in addition to `:latest`, the images
get full semver tags (`:0.2.0`, `:0.2`, `:0`) — and a GitHub Release
is auto-created with notes generated from commits since the previous
tag. Pre-releases (`v0.2.0-rc1`) skip `:latest`.

`local-ai` is intentionally **not** published (2.3 GB upstream base,
thin code change — users build locally on first `docker compose
--profile local-ai up`). `worker` reuses the backend image.

### Pulling the published images on your server

Set both image overrides in `.env`:

```env
BACKEND_IMAGE=ghcr.io/your-name/wow-ai-log-analyzer-backend:latest
FRONTEND_IMAGE=ghcr.io/your-name/wow-ai-log-analyzer-frontend:latest
```

Pin a specific release for stability:

```env
BACKEND_IMAGE=ghcr.io/your-name/wow-ai-log-analyzer-backend:0.2.0
FRONTEND_IMAGE=ghcr.io/your-name/wow-ai-log-analyzer-frontend:0.2.0
```

Then deploy:

```powershell
git pull
docker compose pull backend frontend
docker compose up -d
```

`worker` shares `BACKEND_IMAGE`; no separate pull needed.

### Authenticating to ghcr.io

The default `${{ secrets.GITHUB_TOKEN }}` lets the workflow push to
your repo's package namespace. The first push creates the package as
**private**. If your server is the same host that pushed, no extra
auth needed for `docker pull`. From a separate host you'll need a
personal access token with `read:packages` and `docker login ghcr.io`.

When you flip the repo to public later, the package can be set to
public too (Packages → settings → Change visibility). Then:

- `docker pull` works without auth from anywhere
- Storage / bandwidth quotas no longer apply
- You can choose to also push frontend + local-ai images at that point

## 13. Troubleshooting

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
