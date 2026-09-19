from datetime import datetime, timezone
import json
import os
import urllib.request

from ..db import get_connection
from .autopilot import Autopilot
from .ray_client import RayClient, RayUnavailable


class TaskRunner:
    """Execute central AI tasks with persistent RSS project and GitHub context."""

    def __init__(self, autopilot: Autopilot | None = None) -> None:
        self.autopilot = autopilot or Autopilot()
        self.github_token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        self.ray = RayClient()

    def run_next(self) -> dict:
        with get_connection() as conn:
            task = conn.execute(
                "SELECT id, project_id, conversation_id, title, status, operation, arguments, command, context "
                "FROM tasks WHERE status='pending' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if task is None:
                return {"status": "idle"}
            conn.execute(
                "UPDATE tasks SET status='running', updated_at=NOW() WHERE id=%s",
                (task["id"],),
            )
            conn.commit()

        try:
            context = self._load_context(task["project_id"], task["conversation_id"])
            if task["context"]:
                context = f"{context}\nTASK_CONTEXT:\n{task['context']}"
            command = task["command"]
            if isinstance(command, str):
                try:
                    command = json.loads(command)
                except json.JSONDecodeError:
                    command = None

            try:
                if os.getenv("RSS_RAY_EXECUTE_TASKS", "false").lower() not in {"1", "true", "yes"}:
                    raise RayUnavailable("RAY execution is disabled until explicitly enabled")
                result = self.ray.execute(
                    str(task["id"]),
                    self._project_repository(task["project_id"]),
                    task["title"],
                    context,
                    command,
                )
                if result["status"] == "completed":
                    self._finish(
                        task["id"],
                        task["project_id"],
                        "completed",
                        result.get("output", ""),
                        "ray",
                        {
                            "ray_task_id": result["ray_task_id"],
                            "operation": task["operation"],
                            "arguments": task["arguments"] or {},
                        },
                    )
                    return {
                        "status": "completed",
                        "task_id": task["id"],
                        "provider": "ray",
                        "output": result.get("output", ""),
                        "ray_task_id": result["ray_task_id"],
                    }
                raise RuntimeError(result.get("error", "RAY task failed"))
            except RayUnavailable:
                result = self.autopilot.execute(task["title"], context)
                self._finish(task["id"], task["project_id"], "completed", result.output, result.provider)
                return {
                    "status": "completed",
                    "task_id": task["id"],
                    "provider": result.provider,
                    "model": result.model,
                    "output": result.output,
                    "execution_path": "internal-autopilot-fallback",
                }
        except Exception as exc:
            self._finish(task["id"], task["project_id"], "failed", str(exc))
            return {"status": "failed", "task_id": task["id"], "error": str(exc)}

    def _load_context(self, project_id: str | None, conversation_id: int | None) -> str:
        with get_connection() as conn:
            parts: list[str] = []
            repository = None
            if project_id:
                project = conn.execute(
                    "SELECT id, name, repository, enabled, priority FROM projects WHERE id=%s",
                    (project_id,),
                ).fetchone()
                if project:
                    repository = project["repository"]
                    parts.append(
                        f"PROJECT: {project['name']}\n"
                        f"PROJECT_ID: {project['id']}\n"
                        f"REPOSITORY: {project['repository']}\n"
                        f"ENABLED: {project['enabled']}\n"
                        f"PRIORITY: {project['priority']}"
                    )
                memories = conn.execute(
                    "SELECT memory_type, memory_key, content FROM project_memory "
                    "WHERE project_id=%s ORDER BY updated_at DESC LIMIT 30",
                    (project_id,),
                ).fetchall()
                parts.extend(
                    f"MEMORY {r['memory_type']}/{r['memory_key']}: {r['content']}"
                    for r in memories
                )
            if repository:
                github_context = self._github_context(repository)
                if github_context:
                    parts.append(github_context)
            if conversation_id:
                messages = conn.execute(
                    "SELECT role, content FROM messages WHERE conversation_id=%s "
                    "ORDER BY created_at DESC, id DESC LIMIT 20",
                    (conversation_id,),
                ).fetchall()
                parts.extend(
                    f"{r['role'].upper()}: {r['content']}" for r in reversed(messages)
                )
            return "\n".join(parts)

    def _project_repository(self, project_id: str | None) -> str:
        if not project_id:
            return "RSS-AI-Project-Manager"
        with get_connection() as conn:
            row = conn.execute("SELECT repository FROM projects WHERE id=%s", (project_id,)).fetchone()
        return (row["repository"] if row and row["repository"] else "RSS-AI-Project-Manager").split("/")[-1]

    def _github_context(self, repository: str) -> str:
        """Load lightweight live repository context for every central AI task."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "RSS-AI-Project-Manager",
        }
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        try:
            repo = self._github_get(f"https://api.github.com/repos/{repository}", headers)
            commits = self._github_get(
                f"https://api.github.com/repos/{repository}/commits?per_page=5", headers
            )
            issues = self._github_get(
                f"https://api.github.com/repos/{repository}/issues?state=open&per_page=10", headers
            )
            readme = self._github_get(
                f"https://api.github.com/repos/{repository}/readme", headers
            )
            lines = [
                "LIVE GITHUB CONTEXT:",
                f"default_branch={repo.get('default_branch')}",
                f"language={repo.get('language')}",
                f"open_issues={repo.get('open_issues_count')}",
                f"archived={repo.get('archived')}",
                "RECENT_COMMITS:",
            ]
            for commit in commits if isinstance(commits, list) else []:
                message = commit.get("commit", {}).get("message", "").splitlines()[0]
                lines.append(f"- {commit.get('sha', '')[:8]} {message}")
            lines.append("OPEN_ISSUES:")
            for issue in issues if isinstance(issues, list) else []:
                lines.append(f"- #{issue.get('number')} {issue.get('title', '')}")
            if isinstance(readme, dict) and readme.get("content"):
                import base64
                decoded = base64.b64decode(readme["content"]).decode("utf-8", errors="replace")
                lines.append("README_EXCERPT:")
                lines.append(decoded[:6000])
            return "\n".join(lines)
        except Exception as exc:
            return f"GITHUB_CONTEXT_ERROR: {exc}"

    @staticmethod
    def _github_get(url: str, headers: dict) -> dict | list:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def _finish(
        self,
        task_id: int,
        project_id: str | None,
        status: str,
        summary: str,
        provider: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET status=%s, provider=%s, updated_at=%s WHERE id=%s",
                (status, provider, datetime.now(timezone.utc), task_id),
            )
            conn.execute(
                "INSERT INTO activity_log (project_id, event_type, summary, metadata) "
                "VALUES (%s, %s, %s, %s::jsonb)",
                (project_id, "task." + status, summary[:1000], json.dumps({"provider": provider, **(metadata or {})})),
            )
            conn.commit()
