import json
import os
import urllib.request

from ..db import get_connection


class GitHubExecutor:
    """Discovers accessible GitHub repositories and queues one safe maintenance task per project."""

    def __init__(self) -> None:
        self.owner = os.getenv("GITHUB_OWNER", "riyazamra1")
        self.token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")

    def discover_and_queue(self) -> dict:
        repos = self._repos()
        queued = 0
        with get_connection() as conn:
            for repo in repos:
                if repo.get("fork") or repo.get("archived") or repo.get("disabled"):
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
        """List repositories accessible to the authenticated token, including private repos."""
        repos: list[dict] = []
        page = 1
        while True:
            request = urllib.request.Request(
                f"https://api.github.com/user/repos?per_page=100&page={page}&affiliation=owner,collaborator,organization_member&sort=full_name",
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2026-03-10",
                    "User-Agent": "RSS-AI-Project-Manager",
                    **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                batch = json.loads(response.read().decode())
            if not isinstance(batch, list):
                raise RuntimeError(f"GitHub repository API returned unexpected response: {batch}")
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos
