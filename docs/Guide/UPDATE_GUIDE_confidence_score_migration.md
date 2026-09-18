# Update guide — after pulling the confidence-score change (2026-09-19)

> **For the AI agent reading this:** follow the steps below in order, on the teammate's machine,
> from the repository root. Run each check and report its result. Do not skip the checks. Do not
> commit anything. Stop and tell the user if a check fails; don't work around it.

## What changed and why anything is needed

Commit `283927f` added a per-agent confidence score. That needs **one database migration**:
`infra/db/005_confidence_score.sql` adds two columns (`confidence_score`, `confidence_detail`) to
`audit_trace_log`.

**Without it, every database write of a trace fails** with
`column "confidence_score" of relation "audit_trace_log" does not exist`. That breaks queries'
audit trail, login/register and chat saving.

Nothing else needs installing. No Python or npm dependency changed.

---

## Step 1 — Pull

```bash
git pull
```

Check: `ls infra/db/` lists `005_confidence_score.sql`.

## Step 2 — Apply the migration

Postgres runs in Docker (`docker-compose.yml`, host port **5433**, database `orca`). First check that
the container is up:

```bash
docker ps --format "{{.Names}} {{.Image}}"
```

Look for the `postgis/postgis` container. It's usually named `orca-postgres-1`; if it's named
differently, use that name in place of `orca-postgres-1` below. If it isn't running, start it with
`docker compose up -d postgres`.

**Option A — `psql` is installed** (check with `psql --version` in Git Bash). Use the
`DATABASE_URL` from the repo's `.env`:

```bash
DATABASE_URL="<value of DATABASE_URL from .env>" ./infra/db/migrate.sh
```

It prints `apply 005_confidence_score.sql`, then `migrations up to date`.

**Option B — no `psql`** (the usual case on Windows). Run the migration inside the container:

```bash
docker cp infra/db/005_confidence_score.sql orca-postgres-1:/tmp/005.sql
```

```bash
docker exec orca-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d orca -v ON_ERROR_STOP=1 --single-transaction -f /tmp/005.sql -c "INSERT INTO schema_migrations (filename) VALUES ('"'"'005_confidence_score.sql'"'"') ON CONFLICT DO NOTHING;"'
```

Both options are safe to re-run: the SQL uses `ADD COLUMN IF NOT EXISTS`, and neither changes any
data.

**Check** — both columns must be listed:

```bash
docker exec orca-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d orca -tAc "SELECT column_name FROM information_schema.columns WHERE table_name='"'"'audit_trace_log'"'"' AND column_name LIKE '"'"'confidence%'"'"'"'
```

Expected output (any order): `confidence`, `confidence_detail`, `confidence_score`.

## Step 3 — Restart the backend with the new flag

Stop any running backend first (Ctrl+C in its terminal). Then, in a **normal terminal window**, from
`backend/`:

```bash
.venv/Scripts/uvicorn.exe orca.api.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 3
```

(On macOS/Linux the path is `.venv/bin/uvicorn`.)

**Why the flag:** with `--reload`, uvicorn otherwise waits forever for open browser SSE streams
(`/api/notifications/stream`, `/query`) to close before restarting, so the backend silently stops
answering after the first code edit. **On Windows it must run in a real console window**, not
detached: the reloader stops its worker with Ctrl+C, which a process without a console never
receives.

**Check:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/health
```

Expected: `200`.

## Step 4 — Confirm the feature end to end

```bash
curl -s -N -m 180 "localhost:8000/query?q=what%20are%20the%20tides%20at%20Pamban%20today" | grep -o '"confidence_score": [0-9]*' | head -3
```

Expected: three lines like `"confidence_score": 74`. Then open `http://localhost:3000/ask`, ask any
new question, and check that every agent pill has a small coloured **H / M / L** letter on its
top-right corner.

Answers cached before the restart may still show plain ticks until they expire. That's expected;
ask a new question.

---

## Optional — refresh the wave-height map tiles

`data/` isn't in git, so your tiles are whatever you last generated, probably the old 1–7 Sept
run. To show the current forecast (18–24 Sept), from `backend/`:

```bash
.venv/Scripts/python.exe scripts/generate_tiles.py
```

**Let it finish.** It deletes the old tiles before writing the new ones, so stopping it halfway leaves
the wave layer empty until it's run again.

## Not needed

- `pip install` / `npm install` — no dependency changes.
- Any other migration — `001`–`004` are unchanged.

## If something fails

| Symptom | Cause | Fix |
|---|---|---|
| `psql: command not found` | No local psql | Use Option B |
| `No such container: orca-postgres-1` | Different container name | Use the name from `docker ps` |
| `column "confidence_score" ... does not exist` | Migration not applied | Redo Step 2 and its check |
| `/health` hangs or times out after editing a file | Backend started without the flag, or detached | Restart as in Step 3, in a real terminal window |
| Pills show ticks, no letters | Answer came from the query cache | Ask a new question |

Background and the full reasoning: `docs/DLC_implementation_log.md`, entries dated 2026-09-19.
