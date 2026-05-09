# WoW AI Log Analyzer

A self-hosted web app that analyses World of Warcraft raid and Mythic+ logs
from [warcraftlogs.com](https://www.warcraftlogs.com/), compares them per-fight
against the current public top logs of the same class/spec, and produces a
detailed, actionable improvement report (rotation, cooldowns, stats, talents,
gear, …) via a configurable AI provider. Critical DPS/HPS-losing issues are
highlighted prominently; tone is calibrated to the player's WCL parse %.

- **Backend:** FastAPI (Python 3.13+), SQLAlchemy 2 async, Alembic, arq worker
- **Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind + Lucide icons
- **DB / Cache:** PostgreSQL + Redis
- **AI providers:** Anthropic Claude (default), OpenAI / Azure-OpenAI,
  locally-hosted GGUF via llama.cpp on your own GPU, or fully disabled
  — switchable in the admin UI. The local model is managed live from
  the admin panel (model download with progress bar, cache cleanup,
  start/stop) via a small supervisor sidecar — no `.env` edits or
  container rebuilds for model swaps
- **BYOK:** users can plug in their own Anthropic / OpenAI / OpenAI-compatible
  API key in their profile and run analyses against it instead of the
  app-wide provider — keys are stored Fernet-encrypted in Postgres
- **Auth:** Email + password + admin-managed invitations, JWT, optional WCL
  OAuth connection so users can analyse their own private/unlisted logs
- **Captcha:** optional Cloudflare Turnstile on login / register / forgot /
  accept-invite (env-gated, both keys empty = off)
- **Admin tools:** in-UI tier seeding for new raid encounters, live container
  control (opt-in via `ADMIN_DOCKER_CONTROL`), WoW localisation data refresh
- **i18n:** German + English (`next-intl`), full DSGVO/GDPR-conformant
  Imprint + Privacy Policy reachable without login
- **Tooltips:** Native Wowhead `wowhead_power.js` integration with locale links
- **Deployment:** Docker Compose

> Wowhead integration uses the official tooltip script and external links —
> no Blizzard art assets are bundled.

---

## Quick start

```powershell
# 1. Configure
cp .env.example .env
# Edit values — at minimum:
#   SECRET_KEY (long random string, e.g. `openssl rand -hex 64`)
#   WCL_CLIENT_ID + WCL_CLIENT_SECRET   (see docs/WCL_API_SETUP.md)
#   POSTGRES_PASSWORD
#   INITIAL_ADMIN_EMAIL + INITIAL_ADMIN_PASSWORD
#   ANTHROPIC_API_KEY (or switch AI_PROVIDER and configure that one)
#   IMPRINT_* (your address — required for German § 5 DDG)

# 2. Build & start (omits the local-ai container; see SETUP §8 for that)
docker compose up -d --build

# 3. First boot auto-creates the initial admin. Sign in, then immediately
#    rotate the password under your profile.

# 4. Open
#    http://localhost:3000
```

See [docs/SETUP.md](docs/SETUP.md) for the full walkthrough — including how to
opt into the bundled local-AI container on an NVIDIA GPU — and
[docs/WCL_API_SETUP.md](docs/WCL_API_SETUP.md) for obtaining Warcraft Logs API
credentials.

---

## Repository layout

```
.
├── backend/        # FastAPI app, models, services, worker, migrations, tests
├── frontend/       # Next.js 15 app, Tailwind, shadcn/ui, i18n, tests
├── docs/           # Setup + operations docs
├── docker-compose.yml
└── .env.example
```

---

## Development

### Backend

```powershell
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
uv run pytest
```

Migrations:

```powershell
uv run alembic revision --autogenerate -m "add foo"
uv run alembic upgrade head
```

### Frontend

```powershell
cd frontend
npm install
npm run dev          # http://localhost:3000
npm run test
```

---

## Roles

- **User:** paste a WCL link to import a report, run AI analyses on individual
  players per fight (against the app's AI or the user's own BYOK key),
  browse cached top logs, optionally connect their own WCL account to
  analyse private/unlisted logs, hard-delete their account on demand
  (DSGVO Art. 17).
- **Admin:** toggle public registration, send email invitations, manage
  users (incl. hard-delete with last-admin protection), switch / disable
  the active AI provider, manage the local model (download, switch,
  delete cached GGUFs, start/stop inference) live from the UI, seed
  top-log caches for new tier encounters, refresh WoW localisation data,
  and — when explicitly opted in — start/stop/restart compose containers
  from the System card.

## Legal pages

- `/<locale>/legal/imprint` — fully DDG-compliant. Address fields are pulled
  from `NEXT_PUBLIC_IMPRINT_*` in `.env`; empty fields render as visible
  `[Platzhalter]` so missing data is obvious.
- `/<locale>/legal/privacy` — DSGVO/GDPR Datenschutzerklärung covering
  account data, bcrypt password hashes, Fernet-encrypted WCL OAuth tokens
  and BYOK API keys, the AI-provider data flow (local vs. cloud vs.
  user-supplied), Cloudflare Turnstile cookies (when enabled), retention
  and user rights.

Both reachable without login via the Footer.

---

## Security model

This is a self-hosted single-tenant app. The default deployment assumes:

- **HTTPS reverse proxy in front** (Caddy, nginx, Traefik) routing
  `/api/*` to the backend on `127.0.0.1:8000` and `/*` to the frontend
  on `127.0.0.1:3000`. The frontend uses same-origin `/api/*` URLs, so
  no CORS in production. Without a proxy: TLS is missing, and the
  rate-limiter trusts whatever IP shows up in `request.client` rather
  than the real client.
- **Per-IP + per-account rate limits** on `/auth/*` (login, register,
  refresh, password-reset, accept-invite) — Redis-backed, kicks in even
  when Cloudflare Turnstile is disabled.
- **Boot-time refusal** when `APP_ENV=production` is set together with
  any of the placeholder values from `.env.example` (SECRET_KEY,
  POSTGRES_PASSWORD, INITIAL_ADMIN_PASSWORD). The container will exit
  with a clear error rather than silently boot in an exploitable state.
- **Sensitive data at rest**: bcrypt for password hashes, Fernet
  (key-derived from `SECRET_KEY`) for WCL OAuth refresh/access tokens
  and user BYOK API keys. SQLi-resistant via SQLAlchemy ORM throughout.

### Known trade-off: JWT in `localStorage`

Access + refresh tokens are stored in the browser's `localStorage` and
sent as `Authorization: Bearer …`. This avoids CSRF entirely (no
cookie = browsers don't auto-send it cross-origin) but means an XSS on
the same origin can read them. The codebase contains no
`dangerouslySetInnerHTML` and React escapes user-controlled strings by
default; the residual risk comes from third-party scripts (Wowhead's
`wowhead_power.js`) and any future markdown-rendering you might add.
For a more conservative stance, swap the refresh token to an httpOnly +
Secure + SameSite=strict cookie (open issue if you'd like that wired up).

### Optional Docker-socket admin control

Mounting `/var/run/docker.sock` into the backend is **equivalent to
root on the host**. The default `docker-compose.yml` ships the mount
commented behind a setting line — only uncomment it on single-tenant
self-hosted instances where the admin is also the host operator. The
`ADMIN_DOCKER_CONTROL` flag must additionally be `true` for the backend
to actually use the socket, but the mount itself is the larger blast
radius.

---

## License

The application code in this repository is licensed under the MIT license.
World of Warcraft and all related trademarks are © Blizzard Entertainment.
This project is fan-made and not affiliated with or endorsed by Blizzard.
