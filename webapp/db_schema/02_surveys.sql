CREATE TABLE IF NOT EXISTS surveys (
    id TEXT PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    kind TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    schema_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS surveys_updated ON surveys(updated_at DESC);

CREATE TABLE IF NOT EXISTS survey_sessions (
    id TEXT PRIMARY KEY,
    survey_id TEXT REFERENCES surveys(id),
    participant_code TEXT NOT NULL,
    status TEXT NOT NULL,
    current_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS survey_sessions_survey ON survey_sessions(survey_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS survey_sessions_updated ON survey_sessions(updated_at DESC);

CREATE TABLE IF NOT EXISTS legacy_session_responses (
    session_id TEXT NOT NULL REFERENCES survey_sessions(id),
    ordinal INTEGER NOT NULL,
    answered_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (session_id, ordinal)
);

CREATE TABLE IF NOT EXISTS survey_imports (
    batch_id TEXT PRIMARY KEY,
    survey_id TEXT NOT NULL REFERENCES surveys(id),
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS survey_imports_survey ON survey_imports(survey_id, created_at DESC);

CREATE TABLE IF NOT EXISTS survey_responses (
    response_id TEXT PRIMARY KEY,
    survey_id TEXT NOT NULL REFERENCES surveys(id),
    session_id TEXT REFERENCES survey_sessions(id) DEFERRABLE INITIALLY DEFERRED,
    batch_id TEXT REFERENCES survey_imports(batch_id) DEFERRABLE INITIALLY DEFERRED,
    submit_index INTEGER,
    schema_version INTEGER NOT NULL,
    schema_hash TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    origin TEXT NOT NULL,
    rater TEXT NOT NULL,
    stimulus_id TEXT NOT NULL,
    valid INTEGER NOT NULL CHECK(valid IN (0, 1)),
    payload_json TEXT NOT NULL,
    UNIQUE (session_id, submit_index)
);
CREATE INDEX IF NOT EXISTS survey_responses_survey ON survey_responses(survey_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS survey_responses_session ON survey_responses(session_id, submitted_at);
CREATE INDEX IF NOT EXISTS survey_responses_batch ON survey_responses(batch_id);

CREATE TABLE IF NOT EXISTS survey_import_staging (
    token TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS survey_legacy_migration (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    completed_at TEXT NOT NULL
);
