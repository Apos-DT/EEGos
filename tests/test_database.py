import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webapp import db
from webapp.artifact_index import index_records


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        override = patch.dict(os.environ, {"EEG_DB_PATH": str(self.root / "test.sqlite3")})
        override.start()
        self.addCleanup(override.stop)

    def test_password_and_session_tables_enforce_constraints(self):
        with db.transaction(write=True) as conn:
            user_id = conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                ("example-user", "example@example.invalid", "fixture-encoded-hash"),
            ).lastrowid
        with self.assertRaises(sqlite3.IntegrityError), db.transaction(write=True) as conn:
            conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                ("EXAMPLE-USER", "other@example.invalid", "fixture-encoded-hash"),
            )
        with self.assertRaises(sqlite3.IntegrityError), db.transaction(write=True) as conn:
            conn.execute(
                "INSERT INTO auth_sessions (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
                (user_id + 1, "fixture-token-hash", "2099-01-01"),
            )
        with db.transaction() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM auth_sessions").fetchone()[0], 0)

    def test_file_index_updates_and_removes_rows_without_changing_artifacts(self):
        source = self.root / "signal.npz"
        manifest = self.root / "signal.manifest.json"
        source.write_bytes(b"unchanged file data")
        manifest.write_text("initial", encoding="utf-8")
        calls = []

        def inspect(path):
            calls.append(path)
            return {"id": "signal", "source": manifest.read_text(encoding="utf-8")}

        def query(*paths):
            return index_records("fixture", paths, inspect, sidecars=lambda _: (manifest,))

        self.assertEqual(query(source), [{"id": "signal", "source": "initial"}])
        self.assertEqual(query(source), [{"id": "signal", "source": "initial"}])
        self.assertEqual(len(calls), 1)
        manifest.write_text("updated manifest", encoding="utf-8")
        self.assertEqual(query(source)[0]["source"], "updated manifest")
        self.assertEqual(len(calls), 2)
        self.assertEqual(query(), [])
        self.assertEqual(source.read_bytes(), b"unchanged file data")
        with db.transaction() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM file_artifacts").fetchone()[0], 0)
