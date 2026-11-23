"""Shared SQLite connection and schema migrations for this local workspace."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from eeg_emostudio.paths import DATA_DIR

DB_PATH = DATA_DIR / "emostudio.sqlite3"
SCHEMA_DIR = Path(__file__).with_name("db_schema")
_initialized: dict[Path, tuple[int, int]] = {}
_init_lock = Lock()


def database_path(path: str | Path | None = None) -> Path:
    configured = os.environ.get("EEG_DB_PATH", "").strip()
    return Path(path if path is not None else configured or DB_PATH).expanduser().resolve()


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _apply_sql(conn: sqlite3.Connection, source: str) -> None:
    statement = ""
    for line in source.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            conn.execute(statement)
            statement = ""
    if statement.strip():
        raise ValueError("Incomplete SQLite schema statement")


def initialize(path: str | Path | None = None) -> Path:
    """Apply each bundled schema once, in a transaction, before serving traffic."""
    target = database_path(path)
    with _init_lock:
        if target.is_file():
            stat = target.stat()
            if _initialized.get(target) == (stat.st_dev, stat.st_ino):
                return target
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = _connect(target)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(name TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
            applied = {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}
            for migration in sorted(SCHEMA_DIR.glob("*.sql")):
                if migration.name not in applied:
                    _apply_sql(conn, migration.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (migration.name,))
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        stat = target.stat()
        _initialized[target] = (stat.st_dev, stat.st_ino)
    return target


@contextmanager
def transaction(
    path: str | Path | None = None, *, write: bool = False,
) -> Iterator[sqlite3.Connection]:
    """Use one connection per operation, including across worker threads."""
    conn = _connect(initialize(path))
    try:
        if not write:
            conn.execute("PRAGMA query_only = ON")
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
