-- MarineEdge · free AIS path: positions recorded live from aisstream.io by the recorder service.
-- Apply with: psql $DATABASE_URL -f migrations/003_live_ais.sql

-- Live position reports, keyed by MMSI (what AIS actually transmits). imo is filled from the ship's
-- static-data broadcasts (every 6 min) and backfilled for earlier rows once the MMSI→IMO link is known.
CREATE TABLE IF NOT EXISTS ais_live (
  mmsi     INTEGER NOT NULL,
  ts       TIMESTAMPTZ NOT NULL,
  geom     GEOGRAPHY(POINT, 4326) NOT NULL,
  lat      DOUBLE PRECISION NOT NULL,
  lon      DOUBLE PRECISION NOT NULL,
  sog      REAL,
  cog      REAL,
  heading  REAL,
  nav      SMALLINT,
  draught  REAL,
  imo      INTEGER,
  PRIMARY KEY (mmsi, ts)
);
CREATE INDEX IF NOT EXISTS idx_ais_live_imo_ts ON ais_live (imo, ts);
CREATE INDEX IF NOT EXISTS idx_ais_live_ts ON ais_live (ts);
CREATE INDEX IF NOT EXISTS idx_ais_live_geom ON ais_live USING GIST (geom);

-- Latest static data per MMSI (name, IMO, call sign, destination, ETA, draught, dimensions).
CREATE TABLE IF NOT EXISTS mmsi_map (
  mmsi        INTEGER PRIMARY KEY,
  imo         INTEGER,
  name        TEXT,
  callsign    TEXT,
  type_code   SMALLINT,
  destination TEXT,
  eta         TIMESTAMPTZ,
  draught     REAL,
  dim_a       REAL, dim_b REAL, dim_c REAL, dim_d REAL,
  first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mmsi_map_imo ON mmsi_map (imo);
CREATE INDEX IF NOT EXISTS idx_mmsi_map_name ON mmsi_map (upper(name));

-- Drop raw live rows older than 14 months (the analysis window is 12) to keep the table bounded.
-- Run from cron: DELETE FROM ais_live WHERE ts < now() - interval '14 months';
