import json
import time
import urllib.error
import urllib.request

from ..core.config import settings


class RayUnavailable(RuntimeError):
    """RAY is not configured or temporarily unreachable."""


class RayClient:
    """RSS Core control-plane client for queued or direct RAY execution."""

    def __init__(self) -> None:
        self.base_url = settings.rss_core_url.rstrip("/")
        self.token = settings.rss_core_api_token
        self.poll_seconds = max(1, settings.ray_poll_seconds)
        self.timeout = max(5, settings.ray_poll_timeout_seconds)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not self.base_url or not self.token:
            raise RayUnavailable("RSS Core RAY integration is not configured")
        if self.base_url.startswith("http://") and settings.require_https_integrations:
            raise RayUnavailable("HTTPS is required for RSS Core RAY integration")
        data = json.dumps(payload).encode() if payload is not None else None
        if data is not None and len(data) > settings.max_ray_payload_bytes:
            raise RayUnavailable("RAY request payload exceeds the configured security limit")
        request = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Content-Type": "application/json",
                     "User-Agent": "RSS-AI-Project-Manager"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(settings.max_ray_response_bytes + 1)
                if len(raw) > settings.max_ray_response_bytes:
                    raise RayUnavailable("RAY response exceeds the configured security limit")
                try:
                    decoded = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise RayUnavailable("RSS Core returned an invalid RAY JSON response") from exc
                if not isinstance(decoded, dict):
                    raise RayUnavailable("RSS Core returned an unexpected RAY response shape")
                return decoded
        except urllib.error.HTTPError as exc:
            # Do not leak response bodies, credentials, or internal upstream details.
            if exc.code in {401, 403}:
                raise RayUnavailable(f"RSS Core rejected RAY authentication/authorization (HTTP {exc.code})") from exc
            if exc.code in {404, 408, 409, 425, 429, 500, 502, 503, 504}:
                raise RayUnavailable(f"RSS Core RAY endpoint unavailable (HTTP {exc.code})") from exc
            raise RayUnavailable(f"RSS Core RAY request rejected (HTTP {exc.code})") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RayUnavailable(f"RSS Core RAY transport error: {type(exc).__name__}") from exc

    def submit(self, task_id: str, project: str, task: str, context: str, command: list[str] | None = None) -> str:
        if command is None or not command or not all(isinstance(part, str) and part.strip() for part in command):
            raise RayUnavailable("RAY requires an explicit structured command")
        payload = {"id": task_id, "project": project, "task": task,
                   "context": context, "command": command, "priority": "normal"}

        result = self._request("POST", "/api/v1/ray/tasks", payload)
        if result.get("queued") and result.get("task", {}).get("id"):
            return str(result["task"]["id"])

        # RSS Core may be deployed without a Cloudflare Queue binding. In that
        # configuration use the authenticated direct-dispatch control-plane route.
        result = self._request("POST", "/api/v1/ray/dispatch", payload)
        if result.get("dispatched") and result.get("task", {}).get("id"):
            return str(result["task"]["id"])

        raise RayUnavailable("RSS Core could not queue or directly dispatch the RAY task")

    def execute(self, task_id: str, project: str, task: str, context: str, command: list[str] | None = None) -> dict:
        ray_task_id = self.submit(task_id, project, task, context, command)
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            result = self._request("GET", "/api/v1/ray/tasks/" + ray_task_id)
            status = result.get("status")
            if status == "completed":
                return {"status": "completed", "ray_task_id": ray_task_id,
                        "output": result.get("stdout", ""), "model": result.get("model")}
            if status == "failed":
                return {"status": "failed", "ray_task_id": ray_task_id,
                        "error": result.get("error") or result.get("stderr", "RAY task failed")}
            time.sleep(self.poll_seconds)
        return {"status": "failed", "ray_task_id": ray_task_id,
                "error": "RAY task polling timeout"}
