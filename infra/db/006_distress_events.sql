-- ORCA — distress events, for the authority distress queue (plan P4.16).
-- Applied by infra/db/migrate.sh in filename order, after 005_confidence_score.sql.
--
-- A distress query already leaves its full trace in audit_trace_log. This table
-- is the queue on top of it: one row per distress query, with the state an
-- authority moves it through (open -> acknowledged -> closed). The position is
-- SENSITIVE: /api/ops/distress returns it only while the event is not closed,
-- and every read of it is written to the audit trail as a security event.

CREATE TABLE IF NOT EXISTS distress_events (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    query_id         uuid NOT NULL UNIQUE,          -- joins audit_trace_log.query_id
    position         geometry(Point, 4326),         -- NULL when the caller gave none
    place_name       text,
    distress_type    text,                          -- sos_control | text_pattern
    matched_language text,
    matched_phrase   text,
    mrcc_contact     jsonb,                         -- as surfaced to the caller
    state            text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'acknowledged', 'closed')),
    acknowledged_by  uuid REFERENCES users(id) ON DELETE SET NULL,
    acknowledged_at  timestamptz,
    closed_by        uuid REFERENCES users(id) ON DELETE SET NULL,
    closed_at        timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS distress_events_state_idx ON distress_events (state, created_at DESC);
