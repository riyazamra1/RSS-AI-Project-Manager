from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..security import current_workspace, require_workspace_role, audit

router = APIRouter(prefix="/projects/{project_id}/memory", tags=["memory"])

class MemoryUpsert(BaseModel):
    memory_type: str = Field(min_length=1, max_length=80)
    memory_key: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    source: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

def _project(conn, project_id: str, workspace_id: str):
    row = conn.execute("SELECT id FROM projects WHERE id=%s AND workspace_id=%s", (project_id, workspace_id)).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found")

@router.get("")
def list_memory(project_id: str, ctx: dict = Depends(current_workspace)) -> list[dict]:
    with get_connection() as conn:
        _project(conn, project_id, ctx["workspace_id"])
        rows = conn.execute(
            """SELECT id,memory_type,memory_key,content,source,confidence,created_at,updated_at
               FROM project_memory WHERE project_id=%s AND workspace_id=%s ORDER BY updated_at DESC""",
            (project_id, ctx["workspace_id"]),
        ).fetchall()
    return [dict(row) for row in rows]

@router.put("")
def upsert_memory(project_id: str, memory: MemoryUpsert, ctx: dict = Depends(require_workspace_role("developer"))) -> dict:
    with get_connection() as conn:
        _project(conn, project_id, ctx["workspace_id"])
        row = conn.execute(
            """INSERT INTO project_memory(project_id,workspace_id,memory_type,memory_key,content,source,confidence)
               VALUES(%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT(project_id,memory_type,memory_key) DO UPDATE SET content=EXCLUDED.content,source=EXCLUDED.source,confidence=EXCLUDED.confidence,workspace_id=EXCLUDED.workspace_id,updated_at=NOW()
               RETURNING id,project_id,memory_type,memory_key,content,source,confidence,created_at,updated_at""",
            (project_id,ctx["workspace_id"],memory.memory_type,memory.memory_key,memory.content,memory.source,memory.confidence),
        ).fetchone()
        conn.commit()
    audit(ctx["user"],ctx["workspace_id"],"memory.upsert","project_memory",str(row["id"]))
    return dict(row)
