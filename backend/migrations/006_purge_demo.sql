-- MarineEdge · remove what the generated demo fleet left behind on a server.
-- Before 1.0 a fresh server started on the demo provider, so its database can hold generated positions and the
-- alerts, risk rows and analysis rows built from them. A server never shows the demo any more; this clears it so
-- nothing invented can reappear (for example merged into a real ship's track). Runs once (schema_marks);
-- idempotent like every migration here. Team notes are people's own words and are kept.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM schema_marks WHERE name = '006_demo_purged') THEN
    RETURN;
  END IF;

  CREATE TEMP TABLE demo_imos ON COMMIT DROP AS
    SELECT DISTINCT imo FROM fetch_log WHERE provider ILIKE 'mock%' OR provider ILIKE '%generated%'
    UNION
    SELECT DISTINCT imo FROM positions WHERE provider ILIKE 'mock%' OR provider ILIKE '%generated%';

  DELETE FROM positions WHERE provider ILIKE 'mock%' OR provider ILIKE '%generated%';
  DELETE FROM fetch_log WHERE provider ILIKE 'mock%' OR provider ILIKE '%generated%';
  DELETE FROM alerts      WHERE imo IN (SELECT imo FROM demo_imos);
  DELETE FROM vessel_risk WHERE imo IN (SELECT imo FROM demo_imos);
  DELETE FROM reports     WHERE imo IN (SELECT imo FROM demo_imos);
  -- stored analysis rows (rebuilt from real positions whenever a ship is checked)
  DELETE FROM flags      WHERE imo IN (SELECT imo FROM demo_imos);
  DELETE FROM voyages    WHERE imo IN (SELECT imo FROM demo_imos);
  DELETE FROM port_calls WHERE imo IN (SELECT imo FROM demo_imos);
  DELETE FROM vessel_identity_history WHERE imo IN (SELECT imo FROM demo_imos);
  -- watched demo ships the free feed has never heard of
  DELETE FROM watchlist WHERE imo IN (SELECT imo FROM demo_imos)
    AND imo NOT IN (SELECT imo FROM mmsi_map WHERE imo IS NOT NULL);

  INSERT INTO schema_marks (name) VALUES ('006_demo_purged') ON CONFLICT DO NOTHING;
END $$;
