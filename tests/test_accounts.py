import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from webapp.db import transaction
from webapp.main import app


class AccountTest(unittest.TestCase):
    def test_local_setup_approval_and_revocation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"EEG_DB_PATH": str(Path(directory) / "accounts.sqlite")}
        ):
            options = {"headers": {"Origin": "http://testserver"}, "follow_redirects": False}
            admin, researcher = TestClient(app, **options), TestClient(app, **options)
            password = "password-fixture-123"
            registration = {"username": "owner", "email": "owner@example.com",
                            "password": password, "confirmation": password}
            self.assertEqual(admin.get("/system").status_code, 303)
            self.assertEqual(admin.get("/api/health").status_code, 200)
            self.assertEqual(researcher.post("/register", data=registration).status_code, 400)
            with patch("webapp.routers.account._local_setup", return_value=True):
                self.assertEqual(admin.post("/register", data=registration).status_code, 200)
            self.assertEqual(admin.post("/login", data={"identity": "owner", "password": password}).status_code, 303)
            registration.update(username="researcher", email="researcher@example.com")
            self.assertEqual(researcher.post("/register", data=registration).status_code, 200)
            login = {"identity": registration["email"], "password": password}
            self.assertEqual(researcher.post("/login", data=login).status_code, 401)
            with transaction() as db:
                user = db.execute("SELECT id, password_hash FROM users WHERE username='researcher'").fetchone()
                self.assertNotEqual(user["password_hash"], password)
            approval = f"/accounts/{user['id']}/approve"
            form = {"Content-Type": "application/x-www-form-urlencoded"}
            self.assertEqual(admin.post(approval, headers={**form, "Origin": "https://example.com"}).status_code, 403)
            self.assertEqual(admin.post(approval, headers=form).status_code, 303)
            self.assertEqual(researcher.post("/login", data=login).status_code, 303)
            self.assertEqual(researcher.get("/accounts").status_code, 403)
            token = researcher.cookies.get("emostudio_session")
            self.assertEqual(researcher.post("/logout", headers=form).status_code, 303)
            researcher.cookies.set("emostudio_session", token)
            self.assertEqual(researcher.get("/api/overview").status_code, 401)
