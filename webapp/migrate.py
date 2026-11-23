"""Import the workspace's legacy records and verify the resulting database."""

from __future__ import annotations

import json

from .db import initialize, transaction


def migrate_all() -> None:
    from . import dataset_catalog, eeg, media, record_store, run_store, services, survey_db
    from .routers.raw_eeg import sync_run_index

    initialize()
    survey_db.migrate_legacy()
    media.migrate_legacy()
    record_store.migrate_legacy()
    run_store.migrate_legacy()
    dataset_catalog.migrate_catalog()
    eeg.migrate_legacy()
    services.list_raw_datasets()
    services.list_feature_datasets()
    services.sync_experiments()
    sync_run_index()


def verify() -> dict[str, int]:
    tables = (
        "surveys", "survey_sessions", "survey_responses", "legacy_session_responses",
        "survey_imports", "media_assets", "record_metadata", "record_events", "record_uploads",
        "jobs", "job_logs", "training_observations", "experiment_runs",
        "catalog_sources", "eeg_uploads", "file_artifacts", "users", "auth_sessions",
    )
    with transaction() as conn:
        check = conn.execute("PRAGMA quick_check").fetchone()[0]
        if check != "ok" or conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise RuntimeError("SQLite 数据库完整性检查未通过")
        return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


if __name__ == "__main__":
    migrate_all()
    print(json.dumps({"integrity": "ok", "counts": verify()}, ensure_ascii=False, indent=2))
