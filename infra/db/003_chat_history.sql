-- ORCA — Ask chat history (signed-in users).
-- Applied by infra/db/migrate.sh in filename order, after 002_notifications.sql.
--
-- 001 already models a conversation: `sessions` (one per conversation, owned
-- by a user) and `conversation_turns` (one row per user/assistant message,
-- joined to audit_trace_log by query_id). A saved Ask chat IS one of those
-- sessions, so this extends them instead of adding parallel tables — Sentinel's
-- _write_session_history keeps writing into the same place a chat lives.
--
-- The session id is the chat id the browser mints, which is also the key of
-- the backend's conversational context window (orca/session.py) — one id for
-- the chat, its stored turns and its live context.

ALTER TABLE sessions
    ADD COLUMN title  text,                            -- NULL until named; the UI falls back to the first question
    ADD COLUMN pinned boolean NOT NULL DEFAULT false;

-- The history rail's own ordering: pinned first, then most recently active.
CREATE INDEX sessions_user_history_idx ON sessions (user_id, pinned DESC, last_seen_at DESC);

-- The assistant row's rendered answer (the /query final_response the chat card
-- is built from, minus the bulky audit trace and map layers, which live in
-- audit_trace_log / are recomputed). NULL for rows that were never a chat
-- answer, e.g. Sentinel's "[Sentinel] ..." broadcasts.
ALTER TABLE conversation_turns
    ADD COLUMN payload jsonb;

-- One user row and one assistant row per answered question. Saving a turn is
-- an upsert on this key, so re-saving (a persona re-render, a retried save)
-- updates the row instead of duplicating it. Sentinel's rows use a fresh
-- query_id per broadcast, so they never collide with a chat turn.
CREATE UNIQUE INDEX conversation_turns_session_query_role_uq
    ON conversation_turns (session_id, query_id, role);
