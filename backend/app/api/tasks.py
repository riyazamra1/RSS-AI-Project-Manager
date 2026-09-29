from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..security import current_workspace, require_worker, require_workspace_role, audit

router = APIRouter(prefix="/tasks", tags=["tasks"])

class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    project_id: str | None = None
    conversation_id: int | None = None
    provider: str | None = None
    operation: str | None = Field(default=None, min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)
    command: list[str] | None = None
    context: str | None = Field(default=None, max_length=12000)

def _validate_command(command: list[str] | None):
    if command is None:
        return None
    if not command or len(command) > 32:
        raise HTTPException(422, "command must contain 1-32 arguments")
    if any(not isinstance(part,str) or not part.strip() or len(part)>2048 for part in command):
        raise HTTPException(422, "command arguments must be non-empty strings <= 2048 characters")
    return command

@router.post("", status_code=201)
def create_task(item: TaskCreate, ctx: dict = Depends(current_workspace)) -> dict:
    command = _validate_command(item.command)
    with get_connection() as conn:
        if item.project_id:
            project = conn.execute("SELECT id FROM projects WHERE id=%s AND workspace_id=%s",(item.project_id,ctx["workspace_id"])).fetchone()
            if project is None: raise HTTPException(404,"Project not found")
        if item.conversation_id:
            conversation = conn.execute("SELECT id FROM conversations WHERE id=%s AND workspace_id=%s",(item.conversation_id,ctx["workspace_id"])).fetchone()
            if conversation is None: raise HTTPException(404,"Conversation not found")
        row = conn.execute(
            """INSERT INTO tasks(project_id,conversation_id,workspace_id,title,provider,operation,arguments,command,context)
               VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
               RETURNING id,project_id,conversation_id,title,status,provider,operation,arguments,command,context,created_at,updated_at""",
            (item.project_id,item.conversation_id,ctx["workspace_id"],item.title,item.provider,item.operation,__import__("json").dumps(item.arguments),__import__("json").dumps(command) if command is not None else None,item.context),
        ).fetchone()
        conn.commit()
    audit(ctx["user"],ctx["workspace_id"],"task.create","task",str(row["id"]))
    return dict(row)

@router.get("")
def list_tasks(project_id: str | None = None, ctx: dict = Depends(current_workspace)) -> list[dict]:
    with get_connection() as conn:
        fields="id,project_id,conversation_id,title,status,provider,operation,arguments,command,context,priority,assignee_user_id,due_date,started_at,completed_at,estimate_minutes,position,blocked,created_at,updated_at"
        if project_id:
            rows=conn.execute(f"SELECT {fields} FROM tasks WHERE project_id=%s AND workspace_id=%s ORDER BY created_at DESC",(project_id,ctx["workspace_id"])).fetchall()
        else:
            rows=conn.execute(f"SELECT {fields} FROM tasks WHERE workspace_id=%s ORDER BY created_at DESC",(ctx["workspace_id"],)).fetchall()
    return [dict(row) for row in rows]

@router.post("/run-next")
def run_next_task(_: bool = Depends(require_worker)) -> dict:
    from ..services.task_runner import TaskRunner
    return TaskRunner().run_next()


@router.post("/run-next-user")
def run_next_user_task(ctx: dict = Depends(require_workspace_role("manager"))) -> dict:
    """Run the next approved pending task for the authenticated workspace."""
    from ..services.task_runner import TaskRunner
    result = TaskRunner().run_next()
    if result.get("task_id") is not None:
        with get_connection() as conn:
            row = conn.execute("SELECT workspace_id FROM tasks WHERE id=%s", (result["task_id"],)).fetchone()
        if not row or str(row["workspace_id"]) != str(ctx["workspace_id"]):
            raise HTTPException(403, "Task is outside the current workspace")
    return result
