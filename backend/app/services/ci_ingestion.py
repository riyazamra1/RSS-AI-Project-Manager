import json
import os
import urllib.request

from ..db import get_connection


class CIIngestion:
    """Ingest the latest GitHub Actions result for enabled RSS projects."""

    def __init__(self) -> None:
        self.token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")

    def sync(self) -> dict:
        updated = 0
        checked = 0
        with get_connection() as conn:
            projects = conn.execute(
                "SELECT id, repository FROM projects WHERE enabled=true ORDER BY priority, id"
            ).fetchall()
            for project in projects:
                repository = project["repository"]
                if not repository or "/" not in repository:
                    continue
                run = self._latest_run(repository)
                checked += 1
                if not run:
                    continue
                status = run.get("status") or "unknown"
                conclusion = run.get("conclusion") or "pending"
                summary = f"GitHub Actions CI: status={status}, conclusion={conclusion}"
                metadata = json.dumps({
                    "run_id": run.get("id"),
                    "workflow": run.get("name"),
                    "status": status,
                    "conclusion": conclusion,
                    "sha": run.get("head_sha"),
                    "html_url": run.get("html_url"),
                })
                conn.execute(
                    "INSERT INTO activity_log (project_id, event_type, summary, metadata) "
                    "VALUES (%s, 'ci_result', %s, %s::jsonb)",
                    (project["id"], summary, metadata),
                )
                updated += 1
            conn.commit()
        return {"checked": checked, "updated": updated}

    def _latest_run(self, repository: str) -> dict | None:
        request = urllib.request.Request(
            f"https://api.github.com/repos/{repository}/actions/runs?per_page=1",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "RSS-AI-Project-Manager",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode())
                runs = data.get("workflow_runs", [])
                return runs[0] if runs else None
        except Exception:
            return None
