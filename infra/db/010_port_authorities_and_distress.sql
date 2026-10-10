-- ORCA — coastal authority routing and distress queue enhancements.
-- Applied by infra/db/migrate.sh after 009_pre_dawn_briefing.sql.
--
-- Enables tracking the target port, assigned authority name, and actionable
-- survival suggestions delivered to vessels on distress calls.
ALTER TABLE distress_events
    ADD COLUMN IF NOT EXISTS target_port text,
    ADD COLUMN IF NOT EXISTS authority_name text,
    ADD COLUMN IF NOT EXISTS survival_suggestions jsonb;

CREATE INDEX IF NOT EXISTS distress_events_target_port_idx ON distress_events (target_port, created_at DESC);
