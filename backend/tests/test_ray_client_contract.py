import unittest

from app.services.ray_client import RayClient, RayUnavailable


class RayClientContractTests(unittest.TestCase):
    def setUp(self):
        self.client = RayClient()
        self.client.base_url = "https://rsscore.test"
        self.client.token = "test-token"

    def test_missing_command_is_rejected_before_network(self):
        self.client._request = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("network call not expected")
        )
        with self.assertRaises(RayUnavailable):
            self.client.submit("task-1", "RSS-Test", "natural language task", "context")

    def test_empty_command_is_rejected_before_network(self):
        self.client._request = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("network call not expected")
        )
        with self.assertRaises(RayUnavailable):
            self.client.submit("task-1", "RSS-Test", "task", "context", [])

    def test_reconcile_completed_does_not_submit(self):
        calls = []

        def request(method, path, payload=None):
            calls.append((method, path))
            return {"status": "completed", "stdout": "done"}

        self.client._request = request
        result = self.client.reconcile("ray-existing-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["ray_task_id"], "ray-existing-1")
        self.assertEqual(calls, [("GET", "/api/v1/ray/tasks/ray-existing-1")])

    def test_reconcile_running_keeps_same_identity(self):
        calls = []

        def request(method, path, payload=None):
            calls.append((method, path))
            return {"status": "running", "task": {"id": "ray-existing-2"}}

        self.client._request = request
        result = self.client.reconcile("ray-existing-2")
        self.assertEqual(result["status"], "running")
        self.assertEqual(result["ray_task_id"], "ray-existing-2")
        self.assertEqual(calls, [("GET", "/api/v1/ray/tasks/ray-existing-2")])

    def test_reconcile_not_found_disables_automatic_resubmission(self):
        self.client._request = lambda *args, **kwargs: {
            "status": "not_found",
            "found": False,
        }
        result = self.client.reconcile("ray-missing-1")
        self.assertEqual(result["status"], "not_found")
        self.assertIn("automatic resubmission is disabled", result["error"])

    def test_explicit_command_is_submitted(self):
        captured = {}

        def request(method, path, payload=None):
            captured.update(method=method, path=path, payload=payload)
            return {"queued": True, "task": {"id": "task-1"}}

        self.client._request = request
        task_id = self.client.submit(
            "task-1",
            "riyazamra1/RSS-Test",
            "run checks",
            "context",
            ["python", "-m", "pytest"],
        )

        self.assertEqual(task_id, "task-1")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/api/v1/ray/tasks")
        self.assertEqual(captured["payload"]["command"], ["python", "-m", "pytest"])
        self.assertEqual(captured["payload"]["type"], "CUSTOM")
        self.assertEqual(captured["payload"]["project"], "RSS-Test")
        self.assertEqual(captured["payload"]["capabilities"], ["code"])

    def test_execute_tolerates_worker_404_before_claim(self):
        responses = iter([
            RayUnavailable("RSS Core RAY endpoint unavailable (HTTP 404)"),
            {"status": "completed", "stdout": "worker done"},
        ])
        calls = []

        def request(method, path, payload=None):
            calls.append((method, path))
            if method == "POST":
                return {"queued": True, "task": {"id": "ray-queued-1"}}
            return next(responses)

        self.client._request = request
        self.client.poll_seconds = 0
        self.client.not_found_grace_seconds = 30

        result = self.client.execute(
            "task-1",
            "riyazam1/RSS-Test",
            "run checks",
            "context",
            ["python", "-m", "pytest"],
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["ray_task_id"], "ray-queued-1")
        self.assertEqual(
            calls,
            [
                ("POST", "/api/v1/ray/tasks"),
                ("GET", "/api/v1/ray/tasks/ray-queued-1"),
                ("GET", "/api/v1/ray/tasks/ray-queued-1"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
