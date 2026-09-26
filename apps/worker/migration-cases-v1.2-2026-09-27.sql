-- Additive migration; preserve existing intake, messages and private downloads.
CREATE TABLE IF NOT EXISTS case_reviews (
 session_id TEXT PRIMARY KEY,
 artifact_id TEXT NOT NULL,
 resolution TEXT NOT NULL CHECK(resolution IN ('resolved','needs_more','unconfirmed')),
 execution TEXT NOT NULL CHECK(execution IN ('not_reported','succeeded','failed')),
 allow_publish INTEGER NOT NULL DEFAULT 0 CHECK(allow_publish IN (0,1)),
 revision INTEGER NOT NULL DEFAULT 1,
 updated_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS case_jobs (
 id TEXT PRIMARY KEY,
 session_id TEXT NOT NULL,
 artifact_id TEXT NOT NULL,
 revision INTEGER NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('review_only','publish','retract')),
 status TEXT NOT NULL CHECK(status IN ('pending','processing','completed','needs_review','failed','cancelled')),
 attempts INTEGER NOT NULL DEFAULT 0,
 available_at INTEGER NOT NULL,
 lease_hash TEXT,
 lease_until INTEGER NOT NULL DEFAULT 0,
 worker_id TEXT,
 result TEXT,
 public_url TEXT,
 error_code TEXT,
 created_at INTEGER NOT NULL,
 updated_at INTEGER NOT NULL,
 expires_at INTEGER NOT NULL,
 UNIQUE(session_id,artifact_id,revision,kind)
);
CREATE INDEX IF NOT EXISTS case_jobs_claim_idx ON case_jobs(status,available_at,lease_until);
CREATE INDEX IF NOT EXISTS case_jobs_session_idx ON case_jobs(session_id,created_at);
CREATE TABLE IF NOT EXISTS case_review_requests (
 session_id TEXT NOT NULL,
 request_id TEXT NOT NULL,
 response TEXT NOT NULL,
 created_at INTEGER NOT NULL,
 PRIMARY KEY(session_id,request_id)
);
