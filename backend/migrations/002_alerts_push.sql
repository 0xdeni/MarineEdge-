-- MarineEdge · alerts raised by the watchlist refresh job, and Web Push subscriptions.
-- Apply with: psql $DATABASE_URL -f migrations/002_alerts_push.sql

-- A flag becomes an alert the first time the refresh job sees it. Key = (imo, rule, hour of t0).
CREATE TABLE IF NOT EXISTS alerts (
  id         BIGSERIAL PRIMARY KEY,
  imo        INTEGER NOT NULL,
  rule       TEXT NOT NULL,
  t0_hour    TIMESTAMPTZ NOT NULL,
  severity   TEXT NOT NULL,
  title      TEXT NOT NULL,
  detail     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (imo, rule, t0_hour)
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts(created_at DESC);

CREATE TABLE IF NOT EXISTS push_subscriptions (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id),
  endpoint   TEXT UNIQUE NOT NULL,
  p256dh     TEXT NOT NULL,
  auth       TEXT NOT NULL,
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  failed_at  TIMESTAMPTZ
);

-- Which alerts each user has been shown (for the unread badge).
CREATE TABLE IF NOT EXISTS alert_seen (
  user_id  BIGINT NOT NULL REFERENCES users(id),
  seen_until TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id)
);
