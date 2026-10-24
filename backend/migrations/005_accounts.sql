-- MarineEdge · real accounts (sign up, sign in, password reset, invites), team notes, risk summaries.
-- Idempotent like every migration here: it is re-applied on each update. Apply with:
--   psql $DATABASE_URL -f migrations/005_accounts.sql

-- users existed since 001 (email held the API-token name). Accounts add a password, a status and preferences.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS status        TEXT NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS prefs         JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at  TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at    TIMESTAMPTZ NOT NULL DEFAULT now();

-- One row per signed-in device. Only the SHA-256 of the cookie value is stored.
CREATE TABLE IF NOT EXISTS sessions (
  id           BIGSERIAL PRIMARY KEY,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash   TEXT UNIQUE NOT NULL,
  user_agent   TEXT,
  ip           TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at   TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);

-- Accounts are by invitation. The code travels in a link; only its hash is kept.
CREATE TABLE IF NOT EXISTS invites (
  id         BIGSERIAL PRIMARY KEY,
  code_hash  TEXT UNIQUE NOT NULL,
  email      TEXT,
  role       TEXT NOT NULL DEFAULT 'analyst',
  created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  used_at    TIMESTAMPTZ,
  used_by    BIGINT REFERENCES users(id) ON DELETE SET NULL
);

-- Password resets: a 6-digit code (emailed) and/or a link token (emailed, or made by an admin to share by hand).
CREATE TABLE IF NOT EXISTS password_resets (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash  TEXT,
  token_hash TEXT UNIQUE,
  created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL,
  attempts   INTEGER NOT NULL DEFAULT 0,
  used_at    TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_resets_user ON password_resets(user_id);

-- Team notes, visible to everyone on the server, on a ship ('ship'), a voyage ('voyage:N') or a finding ('flag:KEY').
CREATE TABLE IF NOT EXISTS vessel_notes (
  id         BIGSERIAL PRIMARY KEY,
  imo        INTEGER NOT NULL,
  scope      TEXT NOT NULL DEFAULT 'ship',
  user_id    BIGINT REFERENCES users(id) ON DELETE SET NULL,
  text       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vessel_notes_imo ON vessel_notes(imo, created_at);

-- One-time data moves are recorded here so re-applying a migration never repeats them.
CREATE TABLE IF NOT EXISTS schema_marks (
  name   TEXT PRIMARY KEY,
  run_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO vessel_notes (imo, scope, user_id, text, created_at, updated_at)
  SELECT n.imo, CASE WHEN n.voyage_n IS NULL THEN 'ship' ELSE 'voyage:' || n.voyage_n END, n.user_id, n.text, n.updated_at, n.updated_at
  FROM notes n
  WHERE NOT EXISTS (SELECT 1 FROM schema_marks WHERE name = '005_notes_copied');
INSERT INTO schema_marks (name) VALUES ('005_notes_copied') ON CONFLICT DO NOTHING;

-- The verdict of each ship's latest analysis, for the region overview (counts and the highest-risk list).
CREATE TABLE IF NOT EXISTS vessel_risk (
  imo          INTEGER PRIMARY KEY,
  name         TEXT,
  level        TEXT NOT NULL,              -- high | review | clear | insufficient
  high         INTEGER NOT NULL DEFAULT 0,
  medium       INTEGER NOT NULL DEFAULT 0,
  info         INTEGER NOT NULL DEFAULT 0,
  headline     TEXT,
  sentence     TEXT,
  sanctioned   BOOLEAN NOT NULL DEFAULT false,
  history_days REAL,
  analysed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_vessel_risk_level ON vessel_risk(level, analysed_at);

-- Names each MMSI has broadcast, so a renamed ship is found by its former name and the rename shows as an
-- identity change. Written by the recorder only when a ship's broadcast name changes.
CREATE TABLE IF NOT EXISTS mmsi_names (
  mmsi       BIGINT NOT NULL,
  name       TEXT NOT NULL,
  first_seen TIMESTAMPTZ NOT NULL,
  last_seen  TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (mmsi, name)
);
CREATE INDEX IF NOT EXISTS idx_mmsi_names_name ON mmsi_names (upper(name));
