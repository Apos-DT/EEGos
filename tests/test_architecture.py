"""架构收口相关的回归测试：路径单一来源、缓存失效、管理端令牌。

这三块都是「改坏了不会立刻报错、但会在真实使用中咬人」的地方：
- 路径写错：页面还能渲染，只是读不到新数据；
- 缓存不失效：数据更新后页面还是旧数字；
- 令牌漏配：问卷与答卷对同网段完全裸奔。
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


class PathConfigTest(unittest.TestCase):
    def test_web_aliases_point_at_shared_source(self):
        from eeg_emostudio import paths
        from webapp import config

        self.assertEqual(config.ROOT, paths.PROJECT_ROOT)
        self.assertEqual(config.DATA_DIR, paths.DATA_DIR)
        self.assertEqual(config.ARTIFACTS, paths.ARTIFACTS_DIR)
        self.assertEqual(config.VIDEO_DIR, paths.VIDEO_DIR)
        self.assertEqual(config.AUDIO_DIR, paths.AUDIO_DIR)
        self.assertEqual(config.SURVEYS_DIR, paths.SURVEYS_DIR)
        self.assertEqual(config.RESPONSES_DIR, paths.SURVEY_RESPONSES_DIR)
        self.assertEqual(config.SESSIONS_DIR, paths.SESSIONS_DIR)
        self.assertEqual(config.SELECTION_CSV, paths.SELECTED_MATERIALS_CSV)

    def test_runtime_dirs_are_created(self):
        from eeg_emostudio import paths

        paths.ensure_dirs()
        for directory in (
            paths.DATA_DIR,
            paths.SURVEY_RESPONSES_DIR,
            paths.SESSIONS_DIR,
            paths.SELECTION_DIR,
        ):
            self.assertTrue(directory.is_dir(), str(directory))

    def test_quality_paths_exist_for_research_inputs(self):
        from eeg_emostudio import paths

        for kind, path in paths.QUALITY_FILES.items():
            self.assertTrue(path.exists(), f"{kind}: {path}")
            self.assertIn("research/quality", paths.QUALITY_RELATIVE[kind])


class CacheTest(unittest.TestCase):
    def setUp(self):
        from webapp import config

        self.config = config
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.config.invalidate("t_demo", "t_iso")
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_recomputes_when_directory_changes(self):
        calls = {"n": 0}

        @self.config.cache_by("t_demo", lambda: self.tmp)
        def load() -> list[str]:
            calls["n"] += 1
            return sorted(item.name for item in self.tmp.glob("*"))

        (self.tmp / "a.txt").write_text("1", encoding="utf-8")
        self.assertEqual(load(), ["a.txt"])
        self.assertEqual(calls["n"], 1)

        # 未变化：命中缓存，不再执行 loader
        self.assertEqual(load(), ["a.txt"])
        self.assertEqual(calls["n"], 1)

        # 新增文件：签名变化，必须重算
        (self.tmp / "b.txt").write_text("2", encoding="utf-8")
        self.assertEqual(load(), ["a.txt", "b.txt"])
        self.assertEqual(calls["n"], 2)

    def test_recomputes_when_file_content_appended(self):
        target = self.tmp / "S1.jsonl"
        target.write_text('{"a":1}\n', encoding="utf-8")
        calls = {"n": 0}

        @self.config.cache_by("t_demo", lambda: self.tmp)
        def count() -> int:
            calls["n"] += 1
            return sum(1 for line in target.read_text(encoding="utf-8").splitlines() if line.strip())

        self.assertEqual(count(), 1)
        with target.open("a", encoding="utf-8") as handle:
            handle.write('{"a":2}\n')
        self.assertEqual(count(), 2)
        self.assertEqual(calls["n"], 2)

    def test_cached_value_is_not_shared_by_reference(self):
        first = self.config.cached("t_iso", 1, lambda: {"rows": [{"value": 1}]})
        first["rows"][0]["value"] = 99  # 模拟调用方就地改写
        second = self.config.cached("t_iso", 1, lambda: {"rows": [{"value": 1}]})
        self.assertEqual(second["rows"][0]["value"], 1)


class AccessTokenTest(unittest.TestCase):
    def setUp(self):
        import webapp.main as main

        self.main = main
        self._original = main.ACCESS_TOKEN

    def tearDown(self):
        self.main.ACCESS_TOKEN = self._original

    def test_no_token_configured_requires_account_login(self):
        self.main.ACCESS_TOKEN = ""
        self.assertEqual(TestClient(self.main.app).get("/", follow_redirects=False).status_code, 303)

    def test_admin_pages_and_apis_require_token(self):
        self.main.ACCESS_TOKEN = "secret"
        client = TestClient(self.main.app)
        self.assertEqual(client.get("/", follow_redirects=False).status_code, 303)
        self.assertEqual(client.get("/api/overview").status_code, 401)
        self.assertEqual(client.get("/?token=wrong", follow_redirects=False).status_code, 303)

    def test_public_survey_and_health_stay_open(self):
        self.main.ACCESS_TOKEN = "secret"
        client = TestClient(self.main.app)
        self.assertEqual(client.get("/api/health").status_code, 200)

    def test_valid_token_is_remembered_in_cookie(self):
        self.main.ACCESS_TOKEN = "secret"
        client = TestClient(self.main.app)
        response = client.get("/?token=secret")
        self.assertEqual(response.status_code, 200)
        self.assertIn("eeg_token", response.headers.get("set-cookie", ""))
        # Cookie 生效后，不带参数也能继续浏览管理端
        self.assertEqual(client.get("/surveys").status_code, 200)
        self.assertEqual(client.get("/api/surveys").status_code, 200)


if __name__ == "__main__":
    unittest.main()
