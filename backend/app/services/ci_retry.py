import os

from ..db import get_connection


class CIRetry:
    """Queue bounded maintenance work when a project's latest CI run fails."""

    def __init__(self) -> None:
        self.max_retries = max(1, int(os.getenv("CI_MAX_RETRIES", "3")))

    def queue_failures(self) -> dict:
        queued = 0
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT ON (project_id) project_id, metadata "
                "FROM activity_log WHERE event_type='ci_result' "
                "ORDER BY project_id, created_at DESC, id DESC"
            ).fetchall()
            for row in rows:
                metadata = row["metadata"] or {}
                if metadata.get("conclusion") not in {"failure", "cancelled", "timed_out"}:
                    continue
                project_id = row["project_id"]
                existing = conn.execute(
                    "SELECT 1 FROM tasks WHERE project_id=%s AND title=%s "
                    "AND status IN ('pending','running') LIMIT 1",
                    (project_id, "Automated CI maintenance retry"),
                ).fetchone()
                if existing:
                    continue
                count = conn.execute(
                    "SELECT count(*) AS n FROM tasks WHERE project_id=%s AND title=%s",
                    (project_id, "Automated CI maintenance retry"),
                ).fetchone()["n"]
                if count >= self.max_retries:
                    continue
                conn.execute(
                    "INSERT INTO tasks (project_id, title, status) VALUES (%s, %s, 'pending')",
                    (project_id, "Automated CI maintenance retry"),
                )
                conn.execute(
                    "INSERT INTO activity_log (project_id, event_type, summary, metadata) "
                    "VALUES (%s, 'ci_retry_queued', %s, %s::jsonb)",
                    (project_id, f"Queued bounded CI maintenance retry {count + 1}/{self.max_retries}",
                     '{"policy":"bounded","auto_merge":false}')
                )
                queued += 1
            conn.commit()
        return {"queued": queued, "max_retries": self.max_retries}
