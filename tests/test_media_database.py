import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webapp import media
from webapp.db import transaction


class MediaDatabaseTests(unittest.TestCase):
    def test_legacy_media_index_preserves_metadata_and_tracks_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            managed = root / "media"
            video = managed / "video"
            video.mkdir(parents=True)
            old = video / "existing.mp4"
            old.write_bytes(b"media fixture")
            source_audio = root / "original-music"
            source_audio.mkdir()
            song = source_audio / "new.mp3"
            manifest = managed / "manifest.json"
            manifest.write_text(json.dumps({
                "generated_at": "2026-11-23T12:00:00",
                "managed_dir": "media",
                "items": [{
                    "id": "video/existing.mp4", "modality": "video", "filename": "existing.mp4",
                    "category": "快乐", "quality_score": 0.8, "selected": True, "selection_rank": 1,
                    "available": True, "managed": True, "size_mb": 1,
                }],
            }, ensure_ascii=False), encoding="utf-8")
            original = manifest.read_bytes()
            with patch.dict(os.environ, {"EEG_DB_PATH": str(root / "app.sqlite3")}), patch.multiple(
                media, ROOT=root, MEDIA_DIR=managed, VIDEO_DIR=video, AUDIO_DIR=managed / "audio",
                MANIFEST=manifest, SOURCE_AUDIO_CANDIDATES=[source_audio],
                SOURCE_VIDEO_CANDIDATES=[root / "original-videos"],
                MAPPING={"video": root / "video.csv", "audio": root / "audio.csv"},
                QUALITY={"video": root / "video-quality.csv", "audio": root / "audio-quality.csv"},
                SELECTED=root / "selected.csv",
            ):
                media.migrate_legacy()
                media.migrate_legacy()
                self.assertEqual(media.item_by_id("video/existing.mp4")["category"], "快乐")
                song.write_bytes(b"an imported song")
                self.assertFalse(media.item_by_id("audio/new.mp3")["managed"])
                self.assertEqual(media.sync_library()["counts"]["managed"], 2)
                self.assertEqual((managed / "audio" / song.name).read_bytes(), song.read_bytes())
                old.unlink()
                offline = media.item_by_id("video/existing.mp4")
                self.assertFalse(offline["available"])
                self.assertEqual(offline["quality_score"], 0.8)
                self.assertEqual(manifest.read_bytes(), original)
                with transaction() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM media_assets").fetchone()[0], 2)
