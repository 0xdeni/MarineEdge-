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
-- These two belong to the original layout only; 004 replaces them (primary key (ts, mmsi), no geom column).
-- Guarded so that re-applying 003 on an upgraded database (every update re-applies all migrations) is a no-op.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = current_schema() AND table_name = 'ais_live' AND column_name = 'geom') THEN
    CREATE INDEX IF NOT EXISTS idx_ais_live_ts ON ais_live (ts);
    CREATE INDEX IF NOT EXISTS idx_ais_live_geom ON ais_live USING GIST (geom);
  END IF;
END $$;

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

-- Receiver coverage: every position report received (before downsampling and type filtering) counts
-- one fix in its 0.5° cell for that day. The AIS-gap rule reads the last 30 days of this table.
CREATE TABLE IF NOT EXISTS coverage_cells (
  cx    INTEGER NOT NULL,     -- floor(lon / 0.5)
  cy    INTEGER NOT NULL,     -- floor(lat / 0.5)
  day   DATE NOT NULL,
  fixes BIGINT NOT NULL DEFAULT 0,
  PRIMARY KEY (cx, cy, day)
);

-- Retention is a job, not a cron SQL line: `python -m app.jobs prune-live` thins rows older than
-- rules.live.full_res_days to one per ship per rules.live.thin_minutes and deletes rows older than
-- rules.live.retention_months. Daily from deploy/cron.d-marineedge.
