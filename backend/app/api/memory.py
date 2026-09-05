from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection

router = APIRouter(prefix="/projects/{project_id}/memory", tags=["memory"])


class MemoryUpsert(BaseModel):
    memory_type: str = Field(min_length=1, max_length=80)
    memory_key: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


@router.get("")
def list_memory(project_id: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, memory_type, memory_key, content, source, confidence, created_at, updated_at "
            "FROM project_memory WHERE project_id = %s ORDER BY updated_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.put("")
def upsert_memory(project_id: str, memory: MemoryUpsert) -> dict:
    with get_connection() as conn:
        project = conn.execute("SELECT 1 FROM projects WHERE id = %s", (project_id,)).fetchone()
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        row = conn.execute(
            "INSERT INTO project_memory "
            "(project_id, memory_type, memory_key, content, source, confidence) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (project_id, memory_type, memory_key) DO UPDATE SET "
            "content = EXCLUDED.content, source = EXCLUDED.source, "
            "confidence = EXCLUDED.confidence, updated_at = NOW() "
            "RETURNING id, project_id, memory_type, memory_key, content, source, confidence, created_at, updated_at",
            (project_id, memory.memory_type, memory.memory_key, memory.content, memory.source, memory.confidence),
        ).fetchone()
        conn.commit()
    return dict(row)
