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
- **AI:** locally-hosted GGUF model via llama.cpp (default), Anthropic Claude,
  or any OpenAI-compatible cloud — switchable via a single `.env` value
- **Auth:** Email + password + admin-managed invitations, JWT, optional WCL
  OAuth connection so users can analyse their own private/unlisted logs
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
#   NEXT_PUBLIC_IMPRINT_* (your address — required for German § 5 DDG)

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
  players per fight, browse cached top logs, optionally connect their own
  WCL account to analyse private/unlisted logs.
- **Admin:** toggle public registration, send email invitations, switch the
  active AI provider, refresh top-log caches, manage WoW localisation data
  imports.

## Legal pages

- `/<locale>/legal/imprint` — fully DDG-compliant. Address fields are pulled
  from `NEXT_PUBLIC_IMPRINT_*` in `.env`; empty fields render as visible
  `[Platzhalter]` so missing data is obvious.
- `/<locale>/legal/privacy` — DSGVO/GDPR Datenschutzerklärung covering
  account data, bcrypt password hashes, encrypted WCL OAuth tokens, the
  AI-provider data flow (local vs. cloud), retention, and user rights.

Both reachable without login via the Footer.

---

## License

The application code in this repository is licensed under the MIT license.
World of Warcraft and all related trademarks are © Blizzard Entertainment.
This project is fan-made and not affiliated with or endorsed by Blizzard.
