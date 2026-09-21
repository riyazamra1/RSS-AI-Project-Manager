from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..db import get_connection
from ..security import current_workspace, require_workspace_role, require_worker, audit

router = APIRouter(prefix="/projects/{project_id}/auto-chat", tags=["automatic project chat"])
ALLOWED_INTERVALS = {15, 20, 30, 60}

class AutoChatUpdate(BaseModel):
    interval_minutes: int = Field(description="Automatic project chat interval: 15, 20, 30, or 60 minutes")
    enabled: bool = True

@router.get("")
def get_schedule(project_id: str, ctx=Depends(current_workspace)) -> dict:
    with get_connection() as conn:
        project = conn.execute("SELECT id FROM projects WHERE id=%s AND workspace_id=%s", (project_id, ctx["workspace_id"])).fetchone()
        if project is None: raise HTTPException(404, "Project not found")
        row = conn.execute("SELECT id,project_id,interval_minutes,enabled,next_run_at,last_run_at,created_at,updated_at FROM project_chat_schedules WHERE project_id=%s AND workspace_id=%s", (project_id,ctx["workspace_id"])).fetchone()
    return dict(row) if row else {"project_id": project_id, "enabled": False, "interval_minutes": None, "next_run_at": None, "last_run_at": None}

@router.put("")
def set_schedule(project_id: str, item: AutoChatUpdate, ctx=Depends(require_workspace_role("developer"))) -> dict:
    if item.interval_minutes not in ALLOWED_INTERVALS: raise HTTPException(422, "interval_minutes must be 15, 20, 30, or 60")
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id=%s AND workspace_id=%s", (project_id,ctx["workspace_id"])).fetchone() is None: raise HTTPException(404, "Project not found")
        row = conn.execute("""INSERT INTO project_chat_schedules(workspace_id,project_id,interval_minutes,enabled,next_run_at,created_by)
            VALUES(%s,%s,%s,%s,NOW() + (%s || ' minutes')::interval,%s)
            ON CONFLICT(workspace_id,project_id) DO UPDATE SET interval_minutes=EXCLUDED.interval_minutes,enabled=EXCLUDED.enabled,
              next_run_at=CASE WHEN EXCLUDED.enabled THEN NOW() + (EXCLUDED.interval_minutes || ' minutes')::interval ELSE NULL END,updated_at=NOW()
            RETURNING id,project_id,interval_minutes,enabled,next_run_at,last_run_at,created_at,updated_at""", (ctx["workspace_id"],project_id,item.interval_minutes,item.enabled,item.interval_minutes,ctx["user"]["id"])).fetchone()
        conn.commit()
    audit(ctx["user"],ctx["workspace_id"],"project.auto_chat.update","project",project_id,{"interval_minutes":item.interval_minutes,"enabled":item.enabled})
    return dict(row)

@router.delete("")
def disable_schedule(project_id: str, ctx=Depends(require_workspace_role("developer"))) -> dict:
    with get_connection() as conn:
        conn.execute("UPDATE project_chat_schedules SET enabled=false,next_run_at=NULL,updated_at=NOW() WHERE project_id=%s AND workspace_id=%s",(project_id,ctx["workspace_id"]))
        conn.commit()
    audit(ctx["user"],ctx["workspace_id"],"project.auto_chat.disable","project",project_id)
    return {"project_id":project_id,"enabled":False}

@router.post("/run-due")
def run_due(_: bool=Depends(require_worker)) -> dict:
    from ..services.auto_chat import AutomaticProjectChat
    return AutomaticProjectChat().run_due()
