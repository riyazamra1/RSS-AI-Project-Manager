import unittest

from app.services.ray_client import RayClient, RayUnavailable


class RayClientContractTests(unittest.TestCase):
    def setUp(self):
        self.client = RayClient()
        self.client.base_url = "https://rsscore.test"
        self.client.token = "test-token"

    def test_missing_command_is_rejected_before_network(self):
        self.client._request = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network call not expected"))
        with self.assertRaises(RayUnavailable):
            self.client.submit("task-1", "RSS-Test", "natural language task", "context")

    def test_empty_command_is_rejected_before_network(self):
        self.client._request = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network call not expected"))
        with self.assertRaises(RayUnavailable):
            self.client.submit("task-1", "RSS-Test", "task", "context", [])

    def test_explicit_command_is_submitted(self):
        captured = {}

        def request(method, path, payload=None):
            captured.update(method=method, path=path, payload=payload)
            return {"queued": True, "task": {"id": "task-1"}}

        self.client._request = request
        task_id = self.client.submit("task-1", "RSS-Test", "run checks", "context", ["python", "-m", "pytest"])

        self.assertEqual(task_id, "task-1")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/api/v1/ray/tasks")
        self.assertEqual(captured["payload"]["command"], ["python", "-m", "pytest"])

    def test_polling_failure_requires_reconciliation(self):
        self.client.submit = lambda *args, **kwargs: "ray-accepted-transport"
        def failing_request(*args, **kwargs):
            raise RayUnavailable("temporary RAY transport failure")
        self.client._request = failing_request
        result = self.client.execute("pm-transport", "riyazamra1/RSS-Test", "task", "context", ["echo", "test"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(result["ray_task_id"], "ray-accepted-transport")

    def test_poll_timeout_requires_reconciliation(self):
        self.client.submit = lambda *args, **kwargs: "ray-accepted-1"
        self.client._request = lambda *args, **kwargs: {"status": "running", "task": {"id": "ray-accepted-1"}}
        self.client.timeout = 0
        result = self.client.execute("pm-1", "riyazamra1/RSS-Test", "task", "context", ["echo", "test"])
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(result["ray_task_id"], "ray-accepted-1")


    def test_completed_reconciliation_never_resubmits(self):
        calls = []

        def request(method, path, payload=None):
            calls.append((method, path, payload))
            return {"status": "completed", "stdout": "done", "model": "test-model"}

        self.client._request = request
        result = self.client.reconcile("ray-complete-1")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["ray_task_id"], "ray-complete-1")
        self.assertEqual(result["output"], "done")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(calls[0][1], "/api/v1/ray/tasks/ray-complete-1")

    def test_missing_reconciliation_is_not_resubmitted(self):
        calls = []

        def request(method, path, payload=None):
            calls.append((method, path, payload))
            return {"found": False, "status": "not_found"}

        self.client._request = request
        self.client.submit = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("reconciliation must never resubmit")
        )

        result = self.client.reconcile("ray-missing-1")

        self.assertEqual(result["status"], "not_found")
        self.assertEqual(result["ray_task_id"], "ray-missing-1")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
