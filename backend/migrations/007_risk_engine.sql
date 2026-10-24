-- 007: which version of the rules wrote a stored verdict. Verdicts from an older version are treated as not checked
-- and re-checked by the background sweep, so a rule fix shows up in the region overview at once. Idempotent.
ALTER TABLE vessel_risk ADD COLUMN IF NOT EXISTS engine TEXT;
