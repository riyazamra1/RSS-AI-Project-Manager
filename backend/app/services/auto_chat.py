import json
from datetime import datetime, timezone

from ..core.config import settings
from ..db import get_connection
from .ai_router import AIProviderRouter


class AutomaticProjectChat:
    def run_due(self, limit: int = 10) -> dict:
        processed = []
        for _ in range(max(1, limit)):
            with get_connection() as conn:
                row = conn.execute("""SELECT s.id,s.workspace_id,s.project_id,s.interval_minutes,p.name,p.description,p.status
                    FROM project_chat_schedules s JOIN projects p ON p.id=s.project_id AND p.workspace_id=s.workspace_id
                    WHERE s.enabled=true AND s.next_run_at IS NOT NULL AND s.next_run_at<=NOW()
                    ORDER BY s.next_run_at,s.id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
                if row is None:
                    break

                # Claim before AI work so another API replica cannot process
                # the same schedule concurrently.
                conn.execute(
                    """UPDATE project_chat_schedules
                       SET next_run_at=NOW() + (%s || ' minutes')::interval,
                           last_run_at=NOW(), updated_at=NOW()
                       WHERE id=%s""",
                    (row["interval_minutes"], row["id"]),
                )
                conn.commit()

            try:
                prompt = (
                    f"You are automatically checking project '{row['name']}'. "
                    "Provide a concise project check-in: current state, recent "
                    "risks/blockers, what should happen next, and any user "
                    "decision needed. Do not claim work was completed unless "
                    "recorded in project data.\n"
                    f"Project status: {row['status']}\n"
                    f"Description: {row['description'] or ''}"
                )
                result = AIProviderRouter().generate(prompt)

                with get_connection() as conn:
                    conv = conn.execute(
                        "INSERT INTO conversations(project_id,workspace_id,title) "
                        "VALUES(%s,%s,%s) RETURNING id",
                        (
                            row["project_id"],
                            row["workspace_id"],
                            f"Automatic project check-in — {row['name']}",
                        ),
                    ).fetchone()
                    conn.execute(
                        "INSERT INTO messages(conversation_id,role,content,provider,model) "
                        "VALUES(%s,'assistant',%s,%s,%s)",
                        (conv["id"], result.content, result.provider, result.model),
                    )
                    metadata = json.dumps(
                        {
                            "provider": result.provider,
                            "interval_minutes": row["interval_minutes"],
                        }
                    )
                    conn.execute(
                        "INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata) "
                        "VALUES(%s,%s,'project.auto_chat',%s,%s::jsonb)",
                        (
                            row["project_id"],
                            row["workspace_id"],
                            "Automatic project check-in generated",
                            metadata,
                        ),
                    )
                    conn.commit()

                processed.append(
                    {
                        "project_id": row["project_id"],
                        "conversation_id": conv["id"],
                        "provider": result.provider,
                        "status": "completed",
                    }
                )
            except Exception as exc:
                # Do not wait for the full 15/20/30/60-minute interval after
                # a transient AI/provider failure. Retry on the next scheduler
                # cycle while keeping the original interval after success.
                with get_connection() as conn:
                    conn.execute(
                        """UPDATE project_chat_schedules
                           SET next_run_at=NOW() + (%s || ' seconds')::interval,
                               updated_at=NOW()
                           WHERE id=%s AND enabled=true""",
                        (settings.auto_chat_retry_seconds, row["id"]),
                    )
                    conn.commit()
                processed.append(
                    {
                        "project_id": row["project_id"],
                        "status": "failed",
                        "error": type(exc).__name__,
                    }
                )

        return {
            "processed": len(processed),
            "items": processed,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
