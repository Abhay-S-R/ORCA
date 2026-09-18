-- ORCA — per-agent confidence score on the audit trail.
-- Applied by infra/db/migrate.sh in filename order, after 004_refresh_tokens.sql.
--
-- orca/confidence_score.py turns each agent's measured factors (status, data
-- age against its freshness class, fallback depth, reading coverage) into a
-- 0-100 score. `confidence` keeps holding the label every surface shows; these
-- two columns keep the number and its factor breakdown so /trace/{query_id}
-- can show a judge the arithmetic for a past query, not only a live one.

ALTER TABLE audit_trace_log
    ADD COLUMN IF NOT EXISTS confidence_score  smallint CHECK (confidence_score BETWEEN 0 AND 100),
    ADD COLUMN IF NOT EXISTS confidence_detail jsonb;
