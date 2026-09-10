import json
import os
import urllib.request

from ..db import get_connection


class GitHubExecutor:
    """Discovers GitHub repositories and queues one safe maintenance task per project."""

    def __init__(self) -> None:
        self.owner = os.getenv("GITHUB_OWNER", "riyazamra1")
        self.token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")

    def discover_and_queue(self) -> dict:
        repos = self._repos()
        queued = 0
        with get_connection() as conn:
            for repo in repos:
                if repo.get("fork"):
                    continue
                project = conn.execute(
                    "SELECT id FROM projects WHERE repository=%s AND enabled=true LIMIT 1",
                    (repo.get("full_name"),),
                ).fetchone()
                if project is None:
                    continue
                existing = conn.execute(
                    "SELECT 1 FROM tasks WHERE project_id=%s AND status IN ('pending','running') "
                    "AND title=%s LIMIT 1",
                    (project["id"], "Automated repository health check"),
                ).fetchone()
                if existing:
                    continue
                conn.execute(
                    "INSERT INTO tasks (project_id, title, status) VALUES (%s, %s, 'pending')",
                    (project["id"], "Automated repository health check"),
                )
                queued += 1
            conn.commit()
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
