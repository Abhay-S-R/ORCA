-- ORCA — Phase 5 part 3: adaptive Sentinel cadence, quiet-hours delivery,
-- and saved voyages (plan P5.17, P5.20, P5.22). Applied after
-- 007_vessel_operational.sql.
--
-- P5.17's geometry columns (watch_point / watch_area) and P5.22's schema
-- (users.quiet_hours, sentinel_subscriptions.escalation) already existed
-- (001_init.sql, 007_vessel_operational.sql) — this migration adds only
-- what genuinely did not: adaptive poll cadence, a hold-for-quiet-hours
-- notification state, and voyages as a first-class saved object.

-- P5.17 — adaptive cadence: poll faster when the last reading was within
-- 20% of the watch's threshold. A per-watch due time, not a global interval
-- change, so one close-to-firing watch never speeds up every other watch's
-- polling too.
ALTER TABLE sentinel_subscriptions
    ADD COLUMN IF NOT EXISTS next_poll_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS sentinel_next_poll_idx ON sentinel_subscriptions (next_poll_at) WHERE enabled;

-- P5.22 — quiet hours hold a non-critical alert rather than dropping or
-- immediately delivering it; `deliver_after` is when a held row becomes due.
-- NULL means "not held" for every pre-existing and every immediately-sent row.
ALTER TYPE notification_status ADD VALUE IF NOT EXISTS 'held';
ALTER TABLE notifications
    ADD COLUMN IF NOT EXISTS deliver_after timestamptz;
CREATE INDEX IF NOT EXISTS notifications_held_idx ON notifications (deliver_after) WHERE status = 'held';

-- ---------------------------------------------------------------------------
-- voyages (plan P5.20, orca_final §8.4, §11.3) — a saved passage plan, distinct
-- from a Sentinel watch: this is the plan itself (route, vessel, departure);
-- promoting it to a watch (below) is what makes Sentinel monitor it en route.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS voyages (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vessel_id     uuid REFERENCES vessels(id) ON DELETE SET NULL,
    name          text,
    -- The waypoint track as planned (SENSITIVE, same class as watch_point/
    -- watch_area — a voyage plan is a place a person goes to and when).
    route         geometry(LineString, 4326) NOT NULL,
    departure_at  timestamptz NOT NULL,
    -- The route watch this voyage was promoted to, if any (P5.17). A voyage
    -- can exist unwatched; deleting the watch must not delete the voyage.
    watch_id      uuid REFERENCES sentinel_subscriptions(id) ON DELETE SET NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS voyages_owner_idx ON voyages (owner_user_id, departure_at DESC);
CREATE INDEX IF NOT EXISTS voyages_route_gix ON voyages USING GIST (route);

DO $$ BEGIN
    CREATE TRIGGER voyages_touch BEFORE UPDATE ON voyages
        FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
