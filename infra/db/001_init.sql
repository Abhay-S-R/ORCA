-- ORCA — initial schema (PostgreSQL 16 + PostGIS 3)
-- Closes verification FLAG 6. Applied by infra/db/migrate.sh in filename order.
--
-- Scope rule: this database holds ORCA's OPERATIONAL state only — who the user is,
-- what they own, what they asked, what we answered, and what we monitor for them.
-- Scientific source data (NetCDF, HDF5, GeoJSON grids, the 18.72 GB data/ tree) stays
-- on the filesystem / object storage and is NEVER copied in here. See plan §5.3.
--
-- SRID 4326 (WGS84 lon/lat) everywhere. Distances use geography casts, not degrees.

CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TYPE persona AS ENUM (
    'fisherman', 'commercial_navigator', 'researcher', 'coastal_authority', 'unresolved'
);
CREATE TYPE user_role AS ENUM ('user', 'authority', 'admin');
CREATE TYPE account_status AS ENUM ('active', 'suspended', 'deleted');

CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- authentication identity. phone is the realistic identifier for coastal users;
    -- email is optional. At least one must be present (see constraint).
    phone_e164      text UNIQUE,
    email           text UNIQUE,
    password_hash   text NOT NULL,              -- argon2id; never plaintext or reversible
    display_name    text,
    role            user_role      NOT NULL DEFAULT 'user',
    default_persona persona        NOT NULL DEFAULT 'unresolved',
    language        text           NOT NULL DEFAULT 'en',   -- BCP-47: ta, hi, ml, en ...
    -- SENSITIVE: registered home port. Never returned to another user. See plan §5.5.
    home_port       geometry(Point, 4326),
    home_port_name  text,
    status          account_status NOT NULL DEFAULT 'active',
    created_at      timestamptz    NOT NULL DEFAULT now(),
    updated_at      timestamptz    NOT NULL DEFAULT now(),
    CONSTRAINT users_identity_present CHECK (phone_e164 IS NOT NULL OR email IS NOT NULL)
);
CREATE INDEX users_home_port_gix ON users USING GIST (home_port);
CREATE INDEX users_role_idx      ON users (role) WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- vessels  (a user owns 0..n vessels)
-- ---------------------------------------------------------------------------
CREATE TYPE vessel_class AS ENUM ('catamaran', 'fibreglass', 'mechanised', 'trawler', 'cargo');

CREATE TABLE vessels (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name              text,
    -- SENSITIVE: registration mark identifies a real boat and its crew.
    registration_no   text UNIQUE,
    class             vessel_class NOT NULL,
    draft_m           numeric(4,2) CHECK (draft_m > 0),   -- required by §4.6 corridor routing
    length_m          numeric(5,2),
    crew_size         smallint,
    -- SENSITIVE: last known position. Readable by the owner, by Sentinel on the owner's
    -- behalf, and by an authority only during an ACTIVE distress. See plan §5.5.
    last_position     geometry(Point, 4326),
    last_position_at  timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX vessels_owner_idx         ON vessels (owner_user_id);
CREATE INDEX vessels_last_position_gix ON vessels USING GIST (last_position);

-- ---------------------------------------------------------------------------
-- sessions + conversation turns  (Architecture §5 session_history)
-- ---------------------------------------------------------------------------
CREATE TABLE sessions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       uuid REFERENCES users(id) ON DELETE CASCADE,  -- NULL = anonymous session
    persona       persona NOT NULL DEFAULT 'unresolved',
    language      text    NOT NULL DEFAULT 'en',
    channel       text    NOT NULL DEFAULT 'web',   -- web | pwa | sms | ivr | ussd (plan §4.9)
    started_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_user_idx ON sessions (user_id, last_seen_at DESC);

CREATE TABLE conversation_turns (
    id            bigserial PRIMARY KEY,
    session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    query_id      uuid NOT NULL,                  -- joins audit_trace_log.query_id
    role          text NOT NULL CHECK (role IN ('user', 'assistant')),
    text_original text,                           -- as typed/spoken, user's language
    text_english  text,                           -- normalized English (Agent 1 ingress)
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX conversation_turns_session_idx ON conversation_turns (session_id, created_at);
CREATE INDEX conversation_turns_query_idx   ON conversation_turns (query_id);

-- ---------------------------------------------------------------------------
-- audit_trace_log  (Architecture §6 AgentResult envelope, §9.18 OTel spans)
-- One row per agent execution. This is the compliance record AND the source of the
-- reasoning-graph UI — one pipeline, two views (plan §4.4).
-- ---------------------------------------------------------------------------
CREATE TYPE confidence_tier  AS ENUM ('HIGH', 'MEDIUM', 'LOW_DATA');
CREATE TYPE execution_status AS ENUM ('ok', 'degraded', 'failed', 'skipped', 'cancelled');

CREATE TABLE audit_trace_log (
    id                bigserial PRIMARY KEY,
    query_id          uuid NOT NULL,
    session_id        uuid REFERENCES sessions(id) ON DELETE SET NULL,
    agent_name        text NOT NULL,
    event             text NOT NULL,        -- agent_start | tool_call | agent_complete | fallback | error
    span_id           text,                 -- OTel span id, for trace correlation
    parent_span_id    text,
    inputs_consumed   jsonb,                -- references/keys, NOT bulk scientific payloads
    outputs           jsonb,                -- small computed values; large payloads by reference
    source_provenance jsonb,                -- [{dataset, acquired_at, freshness_s, authority}]
    confidence        confidence_tier,
    status            execution_status NOT NULL DEFAULT 'ok',
    error_detail      text,
    latency_ms        integer,
    created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_query_idx  ON audit_trace_log (query_id, created_at);
CREATE INDEX audit_agent_idx  ON audit_trace_log (agent_name, created_at DESC);
CREATE INDEX audit_status_idx ON audit_trace_log (status) WHERE status <> 'ok';

-- ---------------------------------------------------------------------------
-- sentinel_subscriptions  (Agent 11 — who is watching what, and how to reach them)
-- ---------------------------------------------------------------------------
CREATE TYPE watch_type AS ENUM (
    'weather', 'wave_height', 'lightning', 'cyclone', 'geofence_approach', 'pfz_shift'
);

CREATE TABLE sentinel_subscriptions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    vessel_id      uuid REFERENCES vessels(id) ON DELETE CASCADE,
    watch_type     watch_type NOT NULL,
    -- SENSITIVE: the location a person watches is a location a person goes to.
    watch_point    geometry(Point, 4326),
    watch_area     geometry(Polygon, 4326),      -- district/authority-scale watches
    radius_km      numeric(6,2),
    thresholds     jsonb NOT NULL DEFAULT '{}',  -- {"wave_height_m": 2.5, "wind_kt": 25}
    channels       text[] NOT NULL DEFAULT '{in_app}',  -- in_app | sms | ivr | ussd (plan §4.9)
    enabled        boolean NOT NULL DEFAULT true,
    last_fired_at  timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sentinel_has_geometry CHECK (watch_point IS NOT NULL OR watch_area IS NOT NULL)
);
CREATE INDEX sentinel_user_idx    ON sentinel_subscriptions (user_id);
CREATE INDEX sentinel_enabled_idx ON sentinel_subscriptions (watch_type) WHERE enabled;
CREATE INDEX sentinel_point_gix   ON sentinel_subscriptions USING GIST (watch_point);
CREATE INDEX sentinel_area_gix    ON sentinel_subscriptions USING GIST (watch_area);

-- ---------------------------------------------------------------------------
-- advisory_feedback  (FLAG 10 — "this advisory looks wrong")
-- Distinct from the persona-correction control, which changes rendering only.
-- ---------------------------------------------------------------------------
CREATE TYPE feedback_kind AS ENUM ('helpful', 'not_accurate', 'report_issue');

CREATE TABLE advisory_feedback (
    id           bigserial PRIMARY KEY,
    query_id     uuid NOT NULL,                 -- joins audit_trace_log.query_id
    session_id   uuid REFERENCES sessions(id) ON DELETE SET NULL,
    user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
    advisory_ref text,                          -- which claim/card, when an answer has several
    kind         feedback_kind NOT NULL,
    comment      text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX advisory_feedback_query_idx ON advisory_feedback (query_id);
CREATE INDEX advisory_feedback_kind_idx  ON advisory_feedback (kind, created_at DESC);

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $fn$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$fn$ LANGUAGE plpgsql;

CREATE TRIGGER users_touch    BEFORE UPDATE ON users    FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER vessels_touch  BEFORE UPDATE ON vessels  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER sentinel_touch BEFORE UPDATE ON sentinel_subscriptions FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
