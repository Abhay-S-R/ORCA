-- ORCA — refresh-token rotation and revocation (plan §5.4).
-- Applied by infra/db/migrate.sh in filename order, after 003_chat_history.sql.
--
-- orca/auth/security.py has always issued a 30-day refresh token, but nothing
-- recorded it, so it could be neither used nor revoked: "sign out" only
-- forgot the token in one browser, and a copied refresh token stayed valid
-- for 30 days regardless. One row per issued refresh token, keyed by its JWT
-- `jti` — never the token itself, so this table is useless to someone who
-- reads it.
--
-- Rotation: each /api/refresh revokes the presented token and issues a new
-- one. Presenting an already-revoked token is treated as theft (the legitimate
-- holder rotated past it) and revokes every live token for that user.

CREATE TABLE refresh_tokens (
    jti         uuid PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    issued_at   timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    revoked_at  timestamptz
);

CREATE INDEX refresh_tokens_user_live_idx ON refresh_tokens (user_id) WHERE revoked_at IS NULL;
