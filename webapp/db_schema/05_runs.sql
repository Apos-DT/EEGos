CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    error TEXT,
    pid INTEGER,
    output_path TEXT,
    params_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    runtime_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_recent ON jobs(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS jobs_kind_recent ON jobs(kind, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);

CREATE TABLE IF NOT EXISTS job_logs (
    id INTEGER PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    recorded_at TEXT,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS job_logs_job ON job_logs(job_id, id DESC);

CREATE TABLE IF NOT EXISTS training_observations (
    output_path TEXT PRIMARY KEY,
    started_at TEXT,
    parameters_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_legacy_imports (
    source_path TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS experiment_runs (
    scope TEXT NOT NULL,
    run_id TEXT NOT NULL,
    output_path TEXT NOT NULL,
    artifact_signature TEXT NOT NULL,
    model TEXT NOT NULL,
    setting TEXT NOT NULL,
    dataset TEXT,
    created_at TEXT NOT NULL,
    accuracy REAL,
    macro_f1 REAL,
    is_demo INTEGER NOT NULL CHECK(is_demo IN (0, 1)),
    summary_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    PRIMARY KEY(scope, run_id)
);
CREATE INDEX IF NOT EXISTS experiment_runs_recent ON experiment_runs(scope, created_at DESC, run_id DESC);
