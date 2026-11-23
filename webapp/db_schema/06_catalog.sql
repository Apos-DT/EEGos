CREATE TABLE catalog_sources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    task TEXT NOT NULL,
    structure TEXT NOT NULL,
    source_url TEXT NOT NULL,
    access TEXT NOT NULL,
    adapter TEXT,
    eeg_workflow_url TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX catalog_sources_order ON catalog_sources (sort_order, id);

CREATE TABLE catalog_source_modalities (
    source_id TEXT NOT NULL REFERENCES catalog_sources(id) ON DELETE CASCADE,
    modality TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    PRIMARY KEY (source_id, modality)
);
CREATE INDEX catalog_source_modality ON catalog_source_modalities (modality);

CREATE TABLE file_artifacts (
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    signature TEXT NOT NULL,
    record_id TEXT,
    payload TEXT,
    PRIMARY KEY (kind, path)
);
CREATE INDEX file_artifacts_record ON file_artifacts (kind, record_id);

CREATE TABLE eeg_uploads (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    set_path TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    fs REAL NOT NULL,
    n_channels INTEGER NOT NULL,
    n_samples INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX eeg_uploads_date ON eeg_uploads (uploaded_at DESC, id DESC);

CREATE TABLE legacy_imports (
    domain TEXT PRIMARY KEY,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
