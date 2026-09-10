from datetime import datetime, timezone

from ..db import get_connection
from .autopilot import Autopilot


class TaskRunner:
    """Persist and execute one queued task using the shared Autopilot."""

    def __init__(self, autopilot: Autopilot | None = None) -> None:
        self.autopilot = autopilot or Autopilot()

    def run_next(self) -> dict:
        with get_connection() as conn:
            task = conn.execute(
                "SELECT id, project_id, conversation_id, title, status FROM tasks "
                "WHERE status='pending' ORDER BY created_at, id LIMIT 1"
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
            result = self.autopilot.execute(task["title"], context)
            self._finish(task["id"], task["project_id"], "completed", result.output)
            return {
                "status": "completed",
                "task_id": task["id"],
                "provider": result.provider,
                "model": result.model,
                "output": result.output,
            }
        except Exception as exc:
            self._finish(task["id"], task["project_id"], "failed", str(exc))
            return {"status": "failed", "task_id": task["id"], "error": str(exc)}

    def _load_context(self, project_id: str | None, conversation_id: int | None) -> str:
        with get_connection() as conn:
            parts: list[str] = []
            if project_id:
                memories = conn.execute(
                    "SELECT memory_type, memory_key, content FROM project_memory "
                    "WHERE project_id=%s ORDER BY updated_at DESC LIMIT 20",
                    (project_id,),
                ).fetchall()
                parts.extend(
                    f"MEMORY {r['memory_type']}/{r['memory_key']}: {r['content']}"
                    for r in memories
                )
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

    def _finish(self, task_id: int, project_id: str | None, status: str, summary: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET status=%s, updated_at=%s WHERE id=%s",
                (status, datetime.now(timezone.utc), task_id),
            )
            conn.execute(
                "INSERT INTO activity_log (project_id, event_type, summary, metadata) "
                "VALUES (%s, %s, %s, %s::jsonb)",
                (project_id, "task." + status, summary[:1000], "{}"),
            )
            conn.commit()
