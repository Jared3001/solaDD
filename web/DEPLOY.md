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
5. **Settings → Networking → Generate Domain** to get the team URL.
6. Every push to the connected branch redeploys automatically.

`$PORT` is provided by Railway and consumed by the `Procfile` start command.

## Notes / limits

- Filled workbooks are written to a temp dir and served by `/api/download`.
  The store keeps the most recent 50 runs (older files are pruned).
- A single run is one request kicking off a background thread; this is sized
  for a small internal team, not high concurrency.
- The pipeline calls live public GIS/Census endpoints. FEMA's service is
  intermittently flaky — a `TOOL-FAIL` on flood is expected occasionally and
  shows red in the UI (re-run, or verify that one field manually).
- `/healthz` returns 200 for uptime checks.
