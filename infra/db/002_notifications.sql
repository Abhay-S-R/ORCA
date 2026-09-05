-- ORCA — notifications feed (Phase 3, D2 — Sentinel / Alerting).
-- Applied by infra/db/migrate.sh in filename order, after 001_init.sql.
--
-- 001 already created sentinel_subscriptions and advisory_feedback (and the
-- watch_type / feedback_kind enums). The only new persistence Phase 3 needs
-- is the in-app notification feed: one row per notification shown to one
-- user, plus its delivery status. Same conventions as 001 throughout —
-- uuid PKs DEFAULT gen_random_uuid(), timestamptz DEFAULT now(),
-- touch_updated_at() for the mutable read/dismiss state.

-- ---------------------------------------------------------------------------
-- notification_status
--   sent      — an implemented channel accepted it (in_app: written + visible)
--   simulated — a channel with no real transport (sms/ivr/ussd); the payload
--               is rendered and stored but NOTHING was transmitted (plan §4.9)
--   failed    — the dispatcher raised or the channel rejected it
-- No hyphens (Postgres enums forbid them), same rule as confidence_tier.
-- ---------------------------------------------------------------------------
CREATE TYPE notification_status AS ENUM ('sent', 'simulated', 'failed');

CREATE TABLE notifications (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- The watch that fired this. NULL for a notification raised outside the
    -- Sentinel loop (e.g. an authority district broadcast from /ops).
    watch_id         uuid REFERENCES sentinel_subscriptions(id) ON DELETE SET NULL,
    -- joins audit_trace_log.query_id — the escalated graph run behind this
    -- notification, so "open the trace" from the feed works (plan §4.10).
    query_id         uuid,
    severity         text NOT NULL DEFAULT 'info'
                       CHECK (severity IN ('info', 'advisory', 'warning', 'danger')),
    title            text NOT NULL,
    body             text NOT NULL,
    channel          text NOT NULL DEFAULT 'in_app'
                       CHECK (channel IN ('in_app', 'sms', 'ivr', 'ussd')),
    status           notification_status NOT NULL DEFAULT 'sent',
    -- The exact channel-rendered payload that was (or would have been) sent —
    -- the Sagar-Vani SMS text, the CAP body, etc. Shown verbatim in the feed
    -- so a SIMULATED dispatch still displays what it would have transmitted.
    rendered_payload jsonb NOT NULL DEFAULT '{}',
    read_at          timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX notifications_user_idx    ON notifications (user_id, created_at DESC);
CREATE INDEX notifications_unread_idx  ON notifications (user_id) WHERE read_at IS NULL;
CREATE INDEX notifications_watch_idx   ON notifications (watch_id);
CREATE INDEX notifications_query_idx   ON notifications (query_id);

CREATE TRIGGER notifications_touch
    BEFORE UPDATE ON notifications
    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
