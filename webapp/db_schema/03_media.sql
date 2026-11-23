CREATE TABLE IF NOT EXISTS media_library_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    generated_at TEXT NOT NULL,
    managed_dir TEXT NOT NULL,
    source_video TEXT NOT NULL,
    source_audio TEXT NOT NULL,
    input_signature TEXT
);

CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    modality TEXT NOT NULL CHECK (modality IN ('video', 'audio')),
    filename TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    original_name TEXT NOT NULL DEFAULT '',
    discrete_label TEXT NOT NULL DEFAULT '',
    quality_score REAL,
    grade TEXT NOT NULL DEFAULT '',
    mean_valence REAL,
    mean_arousal REAL,
    selected INTEGER NOT NULL DEFAULT 0 CHECK (selected IN (0, 1)),
    selection_rank INTEGER NOT NULL DEFAULT 0,
    available INTEGER NOT NULL DEFAULT 0 CHECK (available IN (0, 1)),
    managed INTEGER NOT NULL DEFAULT 0 CHECK (managed IN (0, 1)),
    size_mb REAL NOT NULL DEFAULT 0,
    UNIQUE (modality, filename)
);

CREATE INDEX IF NOT EXISTS media_assets_by_selection
    ON media_assets (modality, selected, selection_rank);
