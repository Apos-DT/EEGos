"""Authenticated client for tests of workspace features."""
from unittest.mock import patch

from fastapi.testclient import TestClient


class WorkspaceClient(TestClient):
    def request(self, *args, **kwargs):
        with patch("webapp.main.accounts.session_user", return_value={
            "id": 1, "username": "fixture", "role": "researcher",
        }):
            return super().request(*args, **kwargs)
