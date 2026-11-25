import unittest
from unittest.mock import patch

from fastapi import FastAPI
from auth_client import WorkspaceClient

from webapp.routers import dashboard_queue


class DashboardQueueTests(unittest.TestCase):
    def test_scoped_activity_uses_catalog_and_deduplicates_managed_training(self):
        dda = {"id": "dda-job", "kind": "external_reproduction", "title": "Managed DDA",
               "status": "running", "params": {}, "runtime": {}, "can_cancel": False}
        custom = {"id": "custom-job", "kind": "train", "title": "Custom features",
                  "status": "queued", "params": {"dataset_id": "local1"}, "runtime": {}, "can_cancel": True}
        child = {"id": "dda-run", "job_id": dda["id"], "title": dda["title"], "status": "running",
                 "dataset": "SEED-IV", "progress": {"fraction": .6}}
        observed = {"id": "external", "job_id": None, "title": "Local process", "status": "running",
                    "dataset": "未记录", "progress": {}}
        snapshot = {"tasks": [child, observed], "process_scan_ok": True}
        features = [{"id": "local1", "path": "custom.npz", "source": "自采"}]
        catalog = [{"id": "seed-iv", "name": "SEED-IV"}]
        with (patch.object(dashboard_queue.manager, "active", return_value=[dda, custom]),
              patch.object(dashboard_queue.training_monitor, "snapshot", return_value=snapshot),
              patch.object(dashboard_queue.dataset_catalog, "list_source_datasets", return_value=catalog),
              patch.object(dashboard_queue.services, "list_feature_datasets", return_value=features),
              patch.object(dashboard_queue.record_store, "decorate_rows", side_effect=lambda _, rows, **kw: rows)):
            all_jobs = dashboard_queue._queue_data("")
            self.assertEqual(len(all_jobs["jobs"]), 3)
            self.assertEqual(all_jobs["running_training_count"], 2)
            self.assertEqual(dashboard_queue._queue_data("seed-iv")["jobs"][0]["id"], dda["id"])
            scoped = dashboard_queue._queue_data("feature:local1")
            self.assertEqual([row["id"] for row in scoped["jobs"]], [custom["id"]])
            self.assertEqual(scoped["running_training_count"], 0)

    def test_cancel_route_requires_confirmation_and_rejects_external_origins(self):
        app = FastAPI()
        app.include_router(dashboard_queue.router)
        endpoint = "/api/dashboard/jobs/id/cancel"
        with WorkspaceClient(app) as client, patch.object(dashboard_queue.manager, "cancel", return_value="cancelling") as cancel:
            self.assertEqual(client.post(endpoint, json={"confirmed": False}).status_code, 422)
            self.assertEqual(client.post(endpoint, json={"confirmed": True},
                                         headers={"Origin": "http://external.example"}).status_code, 403)
            self.assertEqual(client.post(endpoint, content='{"confirmed":true}').status_code, 403)
            cancel.assert_not_called()
            self.assertEqual(client.post(endpoint, json={"confirmed": True},
                                         headers={"Origin": "http://testserver"}).json(), {"status": "cancelling"})
            cancel.assert_called_once_with("id")
