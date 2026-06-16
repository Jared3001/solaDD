# Web front end — run & deploy

A small Flask app that wraps the DD pipeline (`build/collect.py` and
`build/assemblage.py`) so the team can run a site through a browser, watch the
~40 readers fill in live, and download the completed checklist `.xlsx`.

- `web/app.py` — routes + shared-password auth
- `web/jobs.py` — background job runner (reuses the CLI readers verbatim)
- `web/templates/`, `web/static/` — UI

## Run locally

```bash
.venv/bin/pip install -r requirements.txt
APP_PASSWORD=somepassword SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_hex(32))") \
  .venv/bin/gunicorn web.app:app --workers 1 --threads 8 --timeout 300 --bind 127.0.0.1:8000
```

Open http://127.0.0.1:8000, sign in with `APP_PASSWORD`.

> Run with **`--workers 1`**. Jobs live in memory in one process; multiple
> workers would split the job store and break polling.

## Deploy to Railway (GitHub auto-deploy)

1. Push this repo to GitHub (already the remote `origin`).
2. In Railway: **New Project → Deploy from GitHub repo →** pick `solaDD`.
3. Railway builds with `nixpacks.toml` (Python 3.12) and starts the process in
   `Procfile`. No extra config needed.
4. **Variables** tab — set:
   - `APP_PASSWORD` — the shared team password.
   - `SECRET_KEY` — any long random string (signs the login cookie; set a
     stable value so sessions survive restarts).
   - *(optional)* `STARTING_CHECKLISTS` — sites already automated before the
     app started counting (default `9`). The time-saved metric =
     `(STARTING_CHECKLISTS + runs) × MINUTES_PER_CHECKLIST`.
   - *(optional)* `MINUTES_PER_CHECKLIST` — minutes saved per checklist (default `30`).
   - *(optional)* `DATA_DIR` — where filled workbooks + the run counter live.
     Defaults to a temp dir, which resets on every redeploy. Point it at a
     **mounted Railway volume** if you want the time-saved counter and recent
     runs to persist across deploys.
   - *(optional)* `ANTHROPIC_API_KEY` — enables **OM upload** (Claude reads the
     Offering Memorandum PDF and auto-fills deal facts). Without it, the address
     search still works; an uploaded OM just reports "needs ANTHROPIC_API_KEY".
     Costs ~cents–dollars per OM depending on size/model; OM contents are sent to
     the Anthropic API and not persisted server-side.
   - *(optional)* `OM_MODEL` — model for OM extraction (default `claude-opus-4-8`;
     set `claude-sonnet-4-6` or `claude-haiku-4-5` to cut cost).
   - *(optional)* `OM_MAX_MB` — max OM PDF size in MB (default `150`). OMs are
     uploaded via the Anthropic Files API (handles large/scanned decks) and the
     uploaded file is deleted right after extraction.
5. **Settings → Networking → Generate Domain** to get the team URL.
6. **Settings → Healthcheck Path:** `/healthz` (returns plain `200`).
7. Every push to the connected branch redeploys automatically.

`$PORT` is provided by Railway and consumed by the `Procfile` start command.

## What's on the page

- **Time saved** — a banner at the top: `(9 + completed runs) × 30 min`,
  shown in hours. Tune via the env vars above.
- **Recent runs** — the last 10 completed checklists with a re-download link,
  so the team can grab an earlier result without re-running. In-memory; cleared
  on redeploy unless `DATA_DIR` is a persistent volume.
- **Health dot** — top-right indicator that pings `/healthz` every 30s
  (green Online / red Offline).
- **Sources tab** — reference breakdown of where every automated answer comes
  from, grouped by level (federal/national, California statewide, local/
  jurisdictional). The local table shows the Los Angeles vs San Diego source for
  each field. Static content from `jobs.SOURCE_CATALOG`.
- **OM upload** (single-address mode, needs `ANTHROPIC_API_KEY`) — drop the
  Offering Memorandum PDF and Claude extracts deal facts (price, land size,
  unit/tenant mix, escrow dates…). Values **default to the OM** and switch to a
  DD answer only when the DD process finds a different, **cited** value — those
  conflicts are flagged JUDGMENT with both values in the notes. An OM panel shows
  every extracted value with its confidence, result (OM-sourced / agrees / DD
  kept), and the source quote. Leave the address blank to pull it from the OM.

## Notes / limits

- Filled workbooks are written to a temp dir and served by `/api/download`.
  The store keeps the most recent 50 runs (older files are pruned).
- A single run is one request kicking off a background thread; this is sized
  for a small internal team, not high concurrency.
- The pipeline calls live public GIS/Census endpoints. FEMA's service is
  intermittently flaky — a `TOOL-FAIL` on flood is expected occasionally and
  shows red in the UI (re-run, or verify that one field manually).
- `/healthz` returns 200 for uptime checks.
