-- MarineEdge · slimmer ais_live. Idempotent: safe to re-run, and it upgrades a table created by 003.
-- Apply with: psql $DATABASE_URL -f migrations/004_slim_live.sql
--
-- Why: the recorded free feed is by far the biggest table, and small free servers have 30–40 GB disks.
--   * the GEOGRAPHY column and its GIST index duplicated lat/lon; neighbour (STS) queries now use a lat/lon
--     box plus a great-circle distance in plain SQL, inside a time window that the primary key narrows first
--   * lat/lon as REAL (about ±0.5 m at these latitudes) instead of DOUBLE PRECISION
--   * primary key (ts, mmsi) instead of (mmsi, ts): it deduplicates as before AND serves every time-range
--     query (latest positions, neighbours, pruning), so the separate ts index goes
-- Together: roughly 300 → 130 bytes per stored fix, indexes included.
DO $$
BEGIN
  IF to_regclass('ais_live') IS NULL THEN
    RETURN;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = current_schema() AND table_name = 'ais_live' AND column_name = 'geom') THEN
    DROP INDEX IF EXISTS idx_ais_live_geom;
    ALTER TABLE ais_live DROP COLUMN geom;
  END IF;
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = current_schema() AND table_name = 'ais_live' AND column_name = 'lat'
               AND data_type = 'double precision') THEN
    ALTER TABLE ais_live ALTER COLUMN lat TYPE REAL, ALTER COLUMN lon TYPE REAL;
  END IF;
  IF (SELECT a.attname FROM pg_index i
        JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = i.indkey[0]
       WHERE i.indrelid = 'ais_live'::regclass AND i.indisprimary) = 'mmsi' THEN
    ALTER TABLE ais_live DROP CONSTRAINT ais_live_pkey;
    ALTER TABLE ais_live ADD PRIMARY KEY (ts, mmsi);
  END IF;
END $$;

DROP INDEX IF EXISTS idx_ais_live_ts;
