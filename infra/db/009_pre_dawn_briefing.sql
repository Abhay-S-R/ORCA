-- ORCA — pre-dawn departure briefing (plan P5.11, R-NEW-16).
-- Applied by infra/db/migrate.sh after 008_phase5_watches_voyages.sql.
--
-- A registered fisherman's typical departure hour, local 24h clock (e.g. 4
-- for 04:00). NULL means the feature is off for this user — no default hour
-- is assumed, matching every other "missing means missing, never guessed"
-- column in this schema. `last_pre_dawn_briefing_date` is the local calendar
-- date the digest was last sent, so the Sentinel loop fires it once per day
-- rather than on every poll tick after the target time.
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS typical_departure_hour smallint CHECK (typical_departure_hour BETWEEN 0 AND 23),
    ADD COLUMN IF NOT EXISTS last_pre_dawn_briefing_date date;
