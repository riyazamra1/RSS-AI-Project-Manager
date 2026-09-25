import json
from datetime import datetime, timezone

from ..core.config import settings
from ..db import get_connection


class AutomaticProjectChat:
    """Queue automatic project check-ins through RSS Core/RAY.

    This scheduler never calls an AI provider directly. It creates a normal PM
    task; the worker delegates that task exclusively to RSS Core/RAY.
    """

    def run_due(self, limit: int = 10) -> dict:
        processed = []
        for _ in range(max(1, limit)):
            with get_connection() as conn:
                row = conn.execute("""SELECT s.id,s.workspace_id,s.project_id,s.interval_minutes,
                    p.name,p.description,p.status,p.repository
                    FROM project_chat_schedules s JOIN projects p
                      ON p.id=s.project_id AND p.workspace_id=s.workspace_id
                    WHERE s.enabled=true AND s.next_run_at IS NOT NULL AND s.next_run_at<=NOW()
                    ORDER BY s.next_run_at,s.id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
                if row is None:
                    break

                conn.execute(
                    """UPDATE project_chat_schedules
                       SET next_run_at=NOW() + (%s || ' minutes')::interval,
                           last_run_at=NOW(), updated_at=NOW()
                       WHERE id=%s""",
                    (row["interval_minutes"], row["id"]),
                )

                prompt = (
                    f"Automatic project check-in for '{row['name']}'. "
                    "Report current state, recent risks/blockers, the next action, "
                    "and any user decision needed. Do not claim work was completed "
                    "unless recorded in project data.\n"
                    f"Project status: {row['status']}\n"
                    f"Description: {row['description'] or ''}\n"
                    f"Repository: {row['repository'] or ''}"
                )
                task = conn.execute(
                    """INSERT INTO tasks
                       (project_id,conversation_id,workspace_id,title,status,operation,arguments,context)
                       VALUES(%s,NULL,%s,%s,'pending','automatic_project_checkin',%s::jsonb,%s)
                       RETURNING id""",
                    (
                        row["project_id"],
                        row["workspace_id"],
                        f"Automatic project check-in — {row['name']}",
                        json.dumps({"schedule_id": row["id"], "repository": row["repository"]}),
                        prompt,
                    ),
                ).fetchone()
                conn.execute(
                    """INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata)
                       VALUES(%s,%s,'project.auto_chat.queued',%s,%s::jsonb)""",
                    (
                        row["project_id"],
                        row["workspace_id"],
                        "Automatic project check-in queued through RSS Core/RAY",
                        json.dumps({"task_id": task["id"], "execution_path": "rss-core-cloudflare-ray"}),
                    ),
                )
                conn.commit()

                processed.append({
                    "project_id": row["project_id"],
                    "task_id": task["id"],
                    "status": "queued",
                })

        return {
            "processed": len(processed),
            "items": processed,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
