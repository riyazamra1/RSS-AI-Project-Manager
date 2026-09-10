from __future__ import annotations

from ..db import get_connection


def upsert_memory(
    project_id: str,
    memory_type: str,
    memory_key: str,
    content: str,
    source: str | None = None,
    confidence: float = 1.0,
) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO project_memory
               (project_id, memory_type, memory_key, content, source, confidence)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (project_id, memory_type, memory_key)
               DO UPDATE SET content=EXCLUDED.content, source=EXCLUDED.source,
                             confidence=EXCLUDED.confidence, updated_at=NOW()
               RETURNING id, project_id, memory_type, memory_key, content, source,
                         confidence, created_at, updated_at""",
            (project_id, memory_type, memory_key, content, source, confidence),
        ).fetchone()
        conn.commit()
    return dict(row)


def list_memory(project_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id, project_id, memory_type, memory_key, content, source,
                      confidence, created_at, updated_at
               FROM project_memory WHERE project_id=%s
               ORDER BY updated_at DESC""",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]
