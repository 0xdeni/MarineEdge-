-- MarineEdge · PostGIS schema. Apply with: psql $DATABASE_URL -f migrations/001_init.sql
CREATE EXTENSION IF NOT EXISTS postgis;

-- Every vessel is keyed on IMO. Name, flag and MMSI are attributes that change; the IMO does not.
CREATE TABLE IF NOT EXISTS vessels (
  imo            INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,
  mmsi           TEXT,
  callsign       TEXT,
  flag           TEXT,
  type           TEXT,                    -- tanker | bulk | container | gas | other
  sub            TEXT,
  dwt            INTEGER,
  gt             INTEGER,
  loa_m          NUMERIC(6,1),
  beam_m         NUMERIC(5,1),
  built          INTEGER,
  builder        TEXT,
  draught_loaded NUMERIC(4,1),
  draught_ballast NUMERIC(4,1),
  region         TEXT,
  reg_owner      TEXT, ben_owner TEXT, ism TEXT, operator TEXT, class_soc TEXT, pi TEXT,
  service_speed  NUMERIC(4,1),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Identity history: one row per change, so a rename or reflag never loses the past.
CREATE TABLE IF NOT EXISTS vessel_identity_history (
  id        BIGSERIAL PRIMARY KEY,
  imo       INTEGER NOT NULL REFERENCES vessels(imo),
  field     TEXT NOT NULL CHECK (field IN ('name','flag','mmsi','callsign')),
  old_value TEXT,
  new_value TEXT,
  changed_at TIMESTAMPTZ NOT NULL,
  source    TEXT
);
CREATE INDEX IF NOT EXISTS idx_identity_imo ON vessel_identity_history(imo, changed_at);

-- Positions: the paid data. Fetched once per (imo, window) and kept.
CREATE TABLE IF NOT EXISTS positions (
  imo       INTEGER NOT NULL REFERENCES vessels(imo),
  ts        TIMESTAMPTZ NOT NULL,
  geom      GEOGRAPHY(POINT, 4326) NOT NULL,
  lat       DOUBLE PRECISION NOT NULL,
  lon       DOUBLE PRECISION NOT NULL,
  sog       REAL,
  cog       REAL,
  heading   REAL,
  draught   REAL,
  nav       SMALLINT,
  src       CHAR(1),                       -- T terrestrial, S satellite
  provider  TEXT NOT NULL,
  PRIMARY KEY (imo, ts)
);
CREATE INDEX IF NOT EXISTS idx_positions_geom ON positions USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_positions_ts ON positions (ts);

-- Which windows have been fetched, so step 3 is never paid twice.
CREATE TABLE IF NOT EXISTS fetch_log (
  id          BIGSERIAL PRIMARY KEY,
  imo         INTEGER NOT NULL,
  window_from TIMESTAMPTZ NOT NULL,
  window_to   TIMESTAMPTZ NOT NULL,
  provider    TEXT NOT NULL,
  positions   INTEGER NOT NULL,
  credits     INTEGER NOT NULL DEFAULT 0,
  fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fetch_imo ON fetch_log(imo, window_to DESC);

CREATE TABLE IF NOT EXISTS ports (
  id        TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  country   TEXT,
  region    TEXT,
  berth     GEOGRAPHY(POINT, 4326) NOT NULL,
  approach  GEOGRAPHY(POINT, 4326),
  kinds     TEXT,
  major     BOOLEAN DEFAULT false,
  zone_id   TEXT,
  anchorage GEOGRAPHY(POINT, 4326),
  anchorage_radius_nm REAL
);

CREATE TABLE IF NOT EXISTS zones (
  id      TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  basis   TEXT,
  enabled BOOLEAN NOT NULL DEFAULT true,
  geom    GEOGRAPHY(POLYGON, 4326) NOT NULL
);

CREATE TABLE IF NOT EXISTS port_calls (
  id         BIGSERIAL PRIMARY KEY,
  imo        INTEGER NOT NULL REFERENCES vessels(imo),
  port_id    TEXT,
  port_name  TEXT NOT NULL,
  anchorage  BOOLEAN NOT NULL DEFAULT false,
  arrived    TIMESTAMPTZ NOT NULL,
  departed   TIMESTAMPTZ NOT NULL,
  draught_in REAL, draught_out REAL,
  anch_hours REAL DEFAULT 0,
  geom       GEOGRAPHY(POINT, 4326)
);
CREATE INDEX IF NOT EXISTS idx_calls_imo ON port_calls(imo, arrived);

CREATE TABLE IF NOT EXISTS voyages (
  id          BIGSERIAL PRIMARY KEY,
  imo         INTEGER NOT NULL REFERENCES vessels(imo),
  n           INTEGER NOT NULL,
  from_call   BIGINT REFERENCES port_calls(id),
  to_call     BIGINT REFERENCES port_calls(id),
  departed    TIMESTAMPTZ NOT NULL,
  arrived     TIMESTAMPTZ,
  distance_nm INTEGER,
  draught_out REAL, draught_in REAL,
  dark_hours  REAL DEFAULT 0,
  current     BOOLEAN NOT NULL DEFAULT false,
  track       GEOGRAPHY(LINESTRING, 4326)
);
CREATE INDEX IF NOT EXISTS idx_voyages_imo ON voyages(imo, n);

CREATE TABLE IF NOT EXISTS flags (
  id        BIGSERIAL PRIMARY KEY,
  imo       INTEGER NOT NULL REFERENCES vessels(imo),
  voyage_id BIGINT REFERENCES voyages(id),
  rule      TEXT NOT NULL,
  severity  TEXT NOT NULL CHECK (severity IN ('high','medium','info')),
  title     TEXT NOT NULL,
  lines     JSONB NOT NULL,
  t0        TIMESTAMPTZ NOT NULL,
  t1        TIMESTAMPTZ,
  geom      GEOGRAPHY(POINT, 4326),
  evidence  JSONB,                          -- positions before/after
  partner_imo INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_flags_imo ON flags(imo, t0 DESC);
CREATE INDEX IF NOT EXISTS idx_flags_sev ON flags(severity, t0 DESC);

-- Sanctions: one row per (list, imo) listing, kept after delisting with delisted_at set.
CREATE TABLE IF NOT EXISTS sanctions (
  id          BIGSERIAL PRIMARY KEY,
  list_name   TEXT NOT NULL,                -- 'OFAC SDN' | 'EU' | 'UK' | 'OpenSanctions'
  imo         INTEGER NOT NULL,
  vessel_name TEXT,
  programme   TEXT,
  listed_at   DATE,
  delisted_at DATE,
  raw         JSONB,
  refreshed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (list_name, imo)
);
CREATE INDEX IF NOT EXISTS idx_sanctions_imo ON sanctions(imo);

CREATE TABLE IF NOT EXISTS users (
  id         BIGSERIAL PRIMARY KEY,
  email      TEXT UNIQUE NOT NULL,
  name       TEXT,
  org        TEXT,
  role       TEXT DEFAULT 'analyst',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS watchlist (
  user_id   BIGINT NOT NULL REFERENCES users(id),
  imo       INTEGER NOT NULL REFERENCES vessels(imo),
  added_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, imo)
);

CREATE TABLE IF NOT EXISTS notes (
  id        BIGSERIAL PRIMARY KEY,
  user_id   BIGINT NOT NULL REFERENCES users(id),
  imo       INTEGER NOT NULL,
  voyage_n  INTEGER,
  text      TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS reports (
  id         BIGSERIAL PRIMARY KEY,
  imo        INTEGER NOT NULL,
  user_id    BIGINT REFERENCES users(id),
  generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  pdf_path   TEXT,
  summary    JSONB
);
