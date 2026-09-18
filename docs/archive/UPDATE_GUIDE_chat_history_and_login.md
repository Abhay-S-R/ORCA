# Updating your local ORCA to chat history + login

For teammates who **already have ORCA running** and need the latest backend,
database and frontend. It takes about 10 minutes.

## What's new

- **Chat history on Ask.** Past chats sit in a left rail (or a **Chats** button
  on narrow screens), with open, rename, pin, search, export (.md) and delete.
- **Chat memory.** Follow-ups like "what about tomorrow evening?" remember the
  last 5 turns of the same chat, including after reopening an old chat.
- **Accounts.** A **Create account** tab on `/login`, a sign-in / account menu
  in the top bar, and sessions that no longer expire after 15 minutes.
- **Where chats are stored.** Signed out, chats stay in your browser. Signed
  in, they're saved to your account in Postgres and show on any device.
  Browser chats can be moved into the account after signing in.

**New dependencies:** none, in both backend and frontend. **Database:** two new
migrations, `003_chat_history.sql` and `004_refresh_tokens.sql`.

---

## 1. Pull the latest code

```bash
git checkout main
git pull origin main
```

If you have local changes, commit or stash them first (`git stash`, then
`git stash pop` afterwards).

## 2. Check your `.env`

`.env` sits in the **repo root**, next to `.env.example`. Make sure these three
are set:

```dotenv
DATABASE_URL=postgresql://orca:orca@localhost:5433/orca
REDIS_URL=redis://localhost:6379/0
ORCA_JWT_SECRET=<a long random string>
```

`ORCA_JWT_SECRET` is **required**. Without it, register and login fail with a
server error. Generate one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use your own value and don't copy someone else's. Changing it later simply
signs everyone out.

The frontend needs nothing new. It calls `http://localhost:8000` unless you've
set `NEXT_PUBLIC_API_BASE_URL`.

## 3. Start Postgres and Redis

From the repo root:

```bash
docker compose up -d postgres redis
docker compose ps          # postgres should show "healthy"
```

Postgres is on host port **5433**, not 5432.

## 4. Run the database migrations

Migrations are the numbered files in `infra/db/`. Each one runs once and is
recorded in the `schema_migrations` table. The commands below apply only the
missing ones, so **they're safe to run again**.

They run `psql` inside the Postgres container, so you don't need `psql`
installed on your machine. Run them from the **repo root** while Postgres is up.

### 4a. First, check what your database already has

```bash
docker compose exec -T postgres psql -U orca -d orca -c "SELECT to_regclass('users') AS users, to_regclass('notifications') AS notifications, to_regclass('schema_migrations') AS migrations"
docker compose exec -T postgres psql -U orca -d orca -c "SELECT filename FROM schema_migrations ORDER BY 1"
```

| What you see | What to do |
|---|---|
| `users` and `notifications` exist, and the second command lists `001_init.sql` and `002_notifications.sql` | Normal. Go to 4b. |
| `users` exists but the second command errors or lists nothing (tables were created by hand, not via `migrate.sh`) | Mark the existing ones as applied first (below), then 4b. |
| All three columns are empty | Fresh database. Go straight to 4b; it applies everything. |

Marking 001/002 as already applied (only if the tables exist):

```bash
docker compose exec -T postgres psql -U orca -d orca -c "CREATE TABLE IF NOT EXISTS schema_migrations (filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now()); INSERT INTO schema_migrations (filename) VALUES ('001_init.sql') ON CONFLICT DO NOTHING;"
# only if the notifications table exists:
docker compose exec -T postgres psql -U orca -d orca -c "INSERT INTO schema_migrations (filename) VALUES ('002_notifications.sql') ON CONFLICT DO NOTHING;"
```

### 4b. Apply the migrations

**Git Bash / macOS / Linux:**

```bash
docker compose exec -T postgres psql -U orca -d orca -qc "CREATE TABLE IF NOT EXISTS schema_migrations (filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());"

for f in infra/db/[0-9]*.sql; do
  name=$(basename "$f")
  if [ "$(docker compose exec -T postgres psql -U orca -d orca -tAc "SELECT 1 FROM schema_migrations WHERE filename = '$name'")" = "1" ]; then
    echo "skip  $name"; continue
  fi
  echo "apply $name"
  { cat "$f"; echo "INSERT INTO schema_migrations (filename) VALUES ('$name');"; } \
    | docker compose exec -T postgres psql -U orca -d orca -v ON_ERROR_STOP=1 -q --single-transaction \
    || { echo "FAILED on $name"; break; }
done
```

**PowerShell:**

```powershell
docker compose exec -T postgres psql -U orca -d orca -qc "CREATE TABLE IF NOT EXISTS schema_migrations (filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());"

foreach ($f in Get-ChildItem infra/db/*.sql | Where-Object Name -match '^\d' | Sort-Object Name) {
  $name = $f.Name
  $applied = docker compose exec -T postgres psql -U orca -d orca -tAc "SELECT 1 FROM schema_migrations WHERE filename = '$name'"
  if ($applied -eq "1") { "skip  $name"; continue }
  "apply $name"
  docker compose cp $f.FullName "postgres:/tmp/$name" *> $null
  docker compose exec -T postgres psql -U orca -d orca -v ON_ERROR_STOP=1 -q --single-transaction -f "/tmp/$name" -c "INSERT INTO schema_migrations (filename) VALUES ('$name');"
  if ($LASTEXITCODE -ne 0) { "FAILED on $name"; break }
}
```

If you have `psql` installed on your machine, `infra/db/migrate.sh` does the
same thing:
`DATABASE_URL=postgresql://orca:orca@localhost:5433/orca ./infra/db/migrate.sh`.

A `NOTICE: relation "schema_migrations" already exists, skipping` line is
harmless.

### 4c. Confirm

```bash
docker compose exec -T postgres psql -U orca -d orca -c "SELECT filename FROM schema_migrations ORDER BY 1"
```

You should see all four:

```
 001_init.sql
 002_notifications.sql
 003_chat_history.sql
 004_refresh_tokens.sql
```

## 5. Restart the backend and frontend

The backend doesn't need `pip install` again (no new packages). If you've
never installed the full backend requirements, run
`pip install -r backend/requirements.txt` once.

```bash
# terminal 1 — backend
cd backend
uvicorn orca.api.main:app --reload --port 8000

# terminal 2 — frontend
cd frontend
npm install        # no new packages, just keeps node_modules in sync
npm run dev
```

Restart the backend even if it was already running with `--reload`, so it
picks up the new routes and the updated `.env`.

## 6. Check it works

**Backend routes are live:**

```bash
curl -s localhost:8000/openapi.json | grep -o '"/api/chats[^"]*"' | sort -u
```

Expect `/api/chats`, `/api/chats/import`, `/api/chats/{chat_id}` and
`/api/chats/{chat_id}/turns/{query_id}`.

**In the app** (`http://localhost:3000/ask`):

1. Signed out, ask a question. It appears in the **Chats** rail on the left.
   Below 1024px wide, use the **Chats** button instead.
2. Ask a follow-up such as "what about tomorrow evening?". The answer shows
   "Following on from 1 earlier message in this chat".
3. Click **Sign in** (top right), then the **Create account** tab, and register.
4. Back on Ask, the rail offers to save your browser chats to your account.
   Click **Save to account**.
5. Ask a question. The rail footer reads "Saved to your account".
6. Open another browser and sign in with the same account. The same chats are
   there.

## 7. Running the tests (optional)

```bash
cd backend
python -m pytest tests/unit tests/e2e -q
```

- `test_chats.py` and `test_auth.py` need Postgres running. They create
  throwaway accounts and clean them up.
- **Stop your running backend first**, or start it with
  `ORCA_SENTINEL_ENABLED=0`. Otherwise
  `test_notifications.py::test_crossing_fires_once...` fails: the running
  server's Sentinel holds a database lock the test needs.

---

## Things you'll notice after updating

- **You'll be signed out once.** Sessions from before this update have no
  refresh token, so sign in again one time.
- **Your old Ask thread isn't lost.** It's moved automatically into the chat
  history as a chat.
- **Chats asked while signed out don't show when you're signed in** until you
  click **Save to account** in the rail. If you pressed "Not now", a one-line
  "Save to account" link stays in the rail.
- **Answering an identical question instantly shows no agent trace.** That
  answer came from the cache, which doesn't replay the trace.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Register or login gives a 500, backend log says `ORCA_JWT_SECRET not set` | Add `ORCA_JWT_SECRET` to the root `.env` (step 2) and restart the backend. |
| Backend error `relation "refresh_tokens" does not exist` or `column sessions.title does not exist` | Migrations 003/004 aren't applied. Run step 4. |
| Migration fails with `type "persona" already exists` on `001_init.sql` | The tables exist but weren't recorded. Do the "mark as applied" part of 4a, then re-run 4b. |
| `password authentication failed` connecting to Postgres | Something else is on port 5432/5433, often a native Postgres. Check `netstat -ano \| findstr 5433` and confirm `DATABASE_URL` uses port **5433**. |
| `docker compose exec` says `service "postgres" is not running` | `docker compose up -d postgres redis`, and run commands from the repo root. |
| No chat rail on the left | Your window is under 1024px wide. Use the **Chats** button above the chat. |
| Chats don't appear in your account | They were asked while signed out. Sign in and click **Save to account** in the rail. |
| Signed in but chats fail to save ("Not saved yet — retrying") | Backend can't reach Postgres, or migrations are missing. Check steps 3–4 and the backend terminal for the error. |
| `/login` or chat requests fail with CORS / network errors | Backend isn't running on `http://localhost:8000`, or `NEXT_PUBLIC_API_BASE_URL` points elsewhere. |
