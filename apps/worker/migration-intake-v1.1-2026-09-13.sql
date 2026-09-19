CREATE TABLE IF NOT EXISTS intakes (
 session_id TEXT PRIMARY KEY,
 state TEXT NOT NULL,
 updated_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS intakes_expiry_idx ON intakes(expires_at);
