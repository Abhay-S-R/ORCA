#!/usr/bin/env bash
# ORCA migration runner. Applies infra/db/NNN_*.sql in filename order, once each.
# Usage: DATABASE_URL=postgres://... ./infra/db/migrate.sh
# ponytail: plain numbered SQL, no Alembic — there are no ORM models yet. Switch to
# Alembic if/when SQLAlchemy models become the source of truth.
set -euo pipefail
: "${DATABASE_URL:?set DATABASE_URL (see .env.example) — never hard-code credentials}"

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -c \
  'CREATE TABLE IF NOT EXISTS schema_migrations (
     filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());'

for f in "$(dirname "$0")"/[0-9]*.sql; do
  name=$(basename "$f")
  applied=$(psql "$DATABASE_URL" -tAc \
    "SELECT 1 FROM schema_migrations WHERE filename = '$name'")
  if [ "$applied" = "1" ]; then
    echo "skip  $name"
    continue
  fi
  echo "apply $name"
  psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q --single-transaction \
    -f "$f" -c "INSERT INTO schema_migrations (filename) VALUES ('$name');"
done
echo "migrations up to date"
