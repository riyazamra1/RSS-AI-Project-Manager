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


if __name__ == "__main__":
    unittest.main()
