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

The daily worker only refreshes (spec, encounter) pairs that already exist in
the cache. To add a new encounter (e.g. when a new raid tier launches):

```powershell
docker compose exec backend uv run python -m scripts.seed_top_logs <ENCOUNTER_ID>
```

`ENCOUNTER_ID` is the stable numeric ID Warcraft Logs uses internally — copy it
from the URL of the encounter page on https://www.warcraftlogs.com/zones/.

Once seeded, the daily cron job (`TOP_LOGS_CRON`) will keep it fresh
automatically.

## 8. Troubleshooting

- `backend` keeps restarting → `docker compose logs backend`. The most common
  cause is an unset `SECRET_KEY` or unreachable database.
- Wowhead tooltips don't appear → ad blockers can block `wowhead_power.js`.
- Daily top-logs job didn't run → check `docker compose logs worker` and the
  `TOP_LOGS_CRON` value (UTC). Trigger manually from **Admin → Top logs** or
  via the CLI helper above.
- AI analysis returns plain text without findings → Anthropic occasionally
  responds without a JSON object. The analyzer stores the raw text in
  `summary` even then; ask the user to retry.
