# Contributing

Glad you're considering a contribution! Small, focused changes are easiest
to review and ship.

## Quick start

```bash
git clone https://github.com/babatonga/wow-ai-log-analyzer.git
cd wow-ai-log-analyzer
cp .env.example .env             # fill in WCL OAuth + AI keys
docker compose up -d --build
```

Backend listens on `127.0.0.1:8000`, frontend on `127.0.0.1:3000`. The
worker runs in its own container — analyses won't progress without it,
so make sure `docker compose ps` shows `worker` as `Up`.

For local development without rebuilding the image on every change, see
`docs/SETUP.md` and the per-service Dockerfiles.

## Branch / PR flow

- Branch off `master`. Use a descriptive prefix:
  - `fix/<short-name>` for bugfixes
  - `feat/<short-name>` for features
  - `chore/<short-name>` for tooling / docs / no-runtime-effect changes
- Open a PR against `master`. The pull-request template will prompt for
  the test plan.
- CI must pass (the existing GitHub Actions workflow).
- `master` is protected — direct pushes are rejected for non-admins.
  Even the maintainer's day-to-day work goes through a PR; the
  bypass-on-admin permission is there for releases and emergency fixes,
  not for skipping review casually.

## Commit messages

A loose [Conventional Commits](https://www.conventionalcommits.org/)
style — the merge commit's first line gets picked up automatically into
release notes:

```
feat(ai): mana-recovery timeline for healer analyses
fix(wcl): phase transitions in fight-relative seconds
docs(setup): clarify reverse-proxy header forwarding
chore(deps): bump SQLAlchemy to 2.0.36
```

The full commit body is welcome to be long — explain the *why*, list
known limitations, paste a verification snippet. Examples in the repo's
history (run `git log --merges`).

## Testing expectations

There's no automated unit-test harness today — the codebase relies on
running flows end-to-end against real (or seeded) WCL data. Concretely:

- **Backend logic changes**: re-import a real public WCL report and
  confirm the new fields land in Postgres. Helper scripts in
  `backend/scripts/` (e.g. `test_combatant_info.py`) show the pattern.
- **AI prompt / output changes**: trigger an analysis on a real fight
  and paste a redacted sample of the model's output into the PR.
- **UI changes**: screenshots before/after.
- **Migration**: run `alembic upgrade head` against a clean Postgres
  and against a copy of your prod schema to confirm both paths work.

Type / AST sanity:

```bash
python -m py_compile backend/app/**/*.py    # rough import-time check
docker compose run --rm backend uv run pytest -x  # if you add tests later
```

## Versioning + data-version stamps

This repo follows SemVer at the container-tag level. When you change the
*shape* of `report_fights.extras` / `report_players.extras` /
`top_logs.detail_payload` / `wow_localizations`, bump the relevant
version constant in code so the auto-refresh system invalidates old
rows:

- `REPORT_DATA_VERSION` in `backend/app/services/report_service.py`
- `TOP_LOG_DETAIL_VERSION` in `backend/app/services/top_logs_service.py`
- For `wow_localizations`, add the new `kind` value to
  `EXPECTED_KINDS` in `wow_data_service.py` so an upgrade triggers a
  re-pull.

The per-version comment block at the constant has the history — add an
entry, don't replace it.

## License

By contributing you agree to license your contribution under the
project's [MIT License](./LICENSE).
