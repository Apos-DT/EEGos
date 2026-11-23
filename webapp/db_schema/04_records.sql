CREATE TABLE IF NOT EXISTS record_legacy_import (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1)
);

CREATE TABLE IF NOT EXISTS record_metadata (
    resource TEXT NOT NULL,
    record_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags_json)),
    revision INTEGER NOT NULL CHECK (revision >= 0),
    deleted_at TEXT,
    updated_at TEXT,
    PRIMARY KEY (resource, record_id)
);

CREATE INDEX IF NOT EXISTS record_metadata_by_trash
    ON record_metadata (resource, deleted_at);

CREATE TABLE IF NOT EXISTS record_events (
    sequence INTEGER PRIMARY KEY,
    resource TEXT NOT NULL,
    record_id TEXT NOT NULL,
    before_json TEXT NOT NULL CHECK (json_valid(before_json)),
    after_json TEXT NOT NULL CHECK (json_valid(after_json)),
    event_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS record_events_by_record
    ON record_events (resource, record_id, sequence);

CREATE TABLE IF NOT EXISTS record_uploads (
    resource TEXT NOT NULL,
    record_id TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    PRIMARY KEY (resource, record_id)
);
