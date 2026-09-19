CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 lock_id TEXT,
 lock_until INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 session_id TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('user','assistant')),
 content TEXT NOT NULL,
 sources TEXT,
 artifact_id TEXT,
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS messages_session_idx ON messages(session_id,id);
CREATE INDEX IF NOT EXISTS messages_created_idx ON messages(created_at);
CREATE TABLE IF NOT EXISTS artifacts (
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL,
 filename TEXT NOT NULL,
 content TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS artifacts_session_idx ON artifacts(session_id);
CREATE TABLE IF NOT EXISTS quotas (
 key TEXT PRIMARY KEY,
 count INTEGER NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
 session_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(session_id,request_id)
);
CREATE INDEX IF NOT EXISTS requests_created_idx ON requests(created_at);

CREATE TABLE IF NOT EXISTS intakes (
 session_id TEXT PRIMARY KEY,
 state TEXT NOT NULL,
 updated_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS intakes_expiry_idx ON intakes(expires_at);
