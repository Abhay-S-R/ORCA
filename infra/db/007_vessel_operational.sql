-- ORCA — vessel operational fields, active-vessel selection, saved locations.
-- Applied by infra/db/migrate.sh in filename order, after 006_distress_events.sql.
--
-- P3.9 (orca_final §8.1, §15.3): worthwhileness (P5.8), fuel economics (P5.9)
-- and the crew/engine threshold deltas (R-NEW-14) can only be computed from
-- real numbers, never invented ones (Ground Rule 1) — so the columns they
-- need exist now, all nullable. A NULL here means the dependent feature says
-- MISSING, never that a default was assumed.
ALTER TABLE vessels
    ADD COLUMN IF NOT EXISTS cruise_speed_kn numeric(4,1) CHECK (cruise_speed_kn > 0),
    ADD COLUMN IF NOT EXISTS fuel_burn_lph   numeric(6,2) CHECK (fuel_burn_lph > 0),
    ADD COLUMN IF NOT EXISTS engine_count    smallint     CHECK (engine_count >= 0);

-- orca_final §15.3: a user owns several vessels, one is "active" at a time —
-- the one /query's vessel-aware surfaces assume when nothing more specific is
-- given. NULL means no vessel is active yet (a fresh account, or the active
-- one was deleted — ON DELETE SET NULL, never left dangling).
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS active_vessel_id uuid REFERENCES vessels(id) ON DELETE SET NULL;

-- P3.10 (orca_final §15.3): named places a signed-in user checks often — a
-- Fishing Location Centre, a reef, a second landing centre — each a one-tap
-- chip above the /ask composer. A signed-out user gets the same feature from
-- localStorage (frontend/app/ask/chatStore.ts's own pattern); this table is
-- only the signed-in half.
CREATE TABLE IF NOT EXISTS saved_locations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,
    position   geometry(Point, 4326) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS saved_locations_user_idx ON saved_locations (user_id, created_at);
