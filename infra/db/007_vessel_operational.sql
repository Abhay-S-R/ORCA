-- ORCA — vessel operational fields + personalization storage (plan P3.9, P3.10).
-- Applied by infra/db/migrate.sh after 006_distress_events.sql.
--
-- All new columns are nullable: a missing value means the dependent feature
-- (worthwhileness P5.8, fuel economics P5.9, crew/engine threshold deltas
-- R-NEW-14, quiet-hours suppression, per-severity escalation P5.22) says
-- MISSING, not that a default was invented (plan principle 1).

ALTER TABLE vessels
    ADD COLUMN IF NOT EXISTS cruise_speed_kn numeric(5,2) CHECK (cruise_speed_kn > 0),
    ADD COLUMN IF NOT EXISTS fuel_burn_lph   numeric(6,2) CHECK (fuel_burn_lph > 0),
    ADD COLUMN IF NOT EXISTS engine_count    smallint     CHECK (engine_count >= 0);

-- orca_final §15.3 — several vessels, one active. The active one is what a
-- place-less/vessel-less query's thresholds default to (P3.1); SET NULL so
-- deleting the active vessel un-sets the pointer rather than failing.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS active_vessel_id uuid REFERENCES vessels(id) ON DELETE SET NULL,
    -- {"start": "22:00", "end": "06:00", "tz": "Asia/Kolkata"} — a non-critical
    -- alert (Sentinel severity below the escalation floor P5.22 reads) is held
    -- until this window ends rather than fired at 2 a.m. A NULL value means no
    -- quiet hours are set, never that a default window was assumed.
    ADD COLUMN IF NOT EXISTS quiet_hours jsonb;

-- P5.22 — which channel each watch escalates to per severity, e.g.
-- {"CAUTION": ["in_app"], "NO_GO": ["in_app", "sms"]}. Empty object, not NULL,
-- so `thresholds`'s own default pattern (001_init.sql) is followed and a
-- missing key inside it is what "not configured for this severity" means.
ALTER TABLE sentinel_subscriptions
    ADD COLUMN IF NOT EXISTS escalation jsonb NOT NULL DEFAULT '{}';

-- ---------------------------------------------------------------------------
-- saved_locations (plan P3.10, orca_final §15.3) — named places a signed-in
-- user bookmarks for a one-tap verdict, distinct from home_port (exactly one,
-- set at setup) and from a Sentinel watch (P5.17 promotes one of these to a
-- watch; it does not replace this table).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS saved_locations (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       text NOT NULL,          -- in the user's own script, as they typed it
    position   geometry(Point, 4326) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS saved_locations_user_idx ON saved_locations (user_id, created_at);
