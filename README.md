# WoW AI Log Analyzer

A self-hosted web app that analyzes World of Warcraft raid and Mythic+ logs from
[warcraftlogs.com](https://www.warcraftlogs.com/) (or manual uploads), compares
them to current top logs of the same class/spec, and produces a detailed,
actionable improvement report (rotation, stats, trinkets, talents, …) using
Anthropic Claude. Critical DPS/HPS-losing issues are highlighted prominently.

- **Backend:** FastAPI (Python 3.13+), SQLAlchemy 2 async, Alembic, arq worker
- **Frontend:** Next.js 15 (App Router) + TypeScript + Tailwind CSS + shadcn/ui
- **DB / Cache:** PostgreSQL + Redis
- **AI:** Anthropic Claude (Sonnet 4.6 default, Opus 4.7 optional)
- **Auth:** Email + password + admin-managed invitations, JWT
- **i18n:** German + English (`next-intl`)
- **Tooltips:** Native Wowhead `wowhead_power.js` integration with locale links
- **Deployment:** Docker Compose

> Wowhead integration uses the official tooltip script and links — no Blizzard
> art assets are bundled, so there are no copyright concerns.

---

## Quick start

```powershell
# 1. Configure
cp .env.example .env            # edit values, especially SECRET_KEY + WCL keys

# 2. Build & start
docker compose up -d --build

# 3. First run: create the initial admin (auto-created on first boot using
#    INITIAL_ADMIN_EMAIL/INITIAL_ADMIN_PASSWORD if no admin exists). Log in
#    immediately and change the password via the profile page.

# 4. Open
#    http://localhost:3000
```

See [docs/SETUP.md](docs/SETUP.md) for a complete setup walkthrough and
[docs/WCL_API_SETUP.md](docs/WCL_API_SETUP.md) to obtain Warcraft Logs API
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

- **User:** upload / paste a WCL link, see analysis, browse top logs.
- **Admin:** toggle public registration, send email invitations, configure AI
  provider/model, view audit log.

---

## License

The application code in this repository is licensed under the MIT license.
World of Warcraft and all related trademarks are © Blizzard Entertainment.
This project is fan-made and not affiliated with or endorsed by Blizzard.
