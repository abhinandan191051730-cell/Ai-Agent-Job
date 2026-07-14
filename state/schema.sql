CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_hash TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    location TEXT,
    description TEXT,
    url TEXT,
    source TEXT,
    platform TEXT,
    external_id TEXT,
    salary_min REAL,
    salary_max REAL,
    posting_date TEXT,
    score REAL DEFAULT 0,
    status TEXT DEFAULT 'discovered',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES jobs(id),
    status TEXT NOT NULL,
    score REAL,
    platform TEXT,
    error_message TEXT,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rate_limits (
    platform TEXT NOT NULL,
    date TEXT NOT NULL,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (platform, date)
);

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,
    response TEXT NOT NULL,
    model TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS platform_state (
    platform TEXT PRIMARY KEY,
    captcha_count INTEGER DEFAULT 0,
    auth_required INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    run_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    discovered INTEGER DEFAULT 0,
    scored_above_threshold INTEGER DEFAULT 0,
    scored_below_threshold INTEGER DEFAULT 0,
    applied INTEGER DEFAULT 0,
    skipped INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    captcha_blocked INTEGER DEFAULT 0,
    auth_required INTEGER DEFAULT 0,
    by_platform TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_hash ON jobs(unique_hash);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_applications_job ON applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_run_summaries_run ON run_summaries(run_id);
