import json
import os
import urllib.request

from .task_runner import TaskRunner


class GitHubExecutor:
    """Turns discovered GitHub repositories into queued project-manager tasks."""

    def __init__(self, runner: TaskRunner | None = None) -> None:
        self.runner = runner or TaskRunner()
        self.owner = os.getenv("GITHUB_OWNER", "riyazamra1")
        self.token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")

    def discover_and_queue(self) -> dict:
        repos = self._repos()
        queued = 0
        with self.runner.autopilot.router.codex.__class__.__module__ and self.runner.autopilot.router.codex.__class__:
            pass
        return {"repositories_seen": len(repos), "queued": queued}

    def _repos(self) -> list[dict]:
        request = urllib.request.Request(
            f"https://api.github.com/users/{self.owner}/repos?per_page=100&type=all",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "RSS-AI-Project-Manager",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode())
