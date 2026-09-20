from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..security import require_auth, workspace_access

router = APIRouter(prefix="/pm", tags=["productivity"])


def current_workspace(
    workspace_id: str | None = Header(default=None, alias="X-Workspace-ID"),
    user: dict = Depends(require_auth),
) -> tuple[dict, str]:
    if not workspace_id:
        raise HTTPException(400, "X-Workspace-ID is required")
    workspace = workspace_access(user, workspace_id)
    return user, workspace_id


class MilestoneCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: str = Field(default="planned", pattern="^(planned|active|completed|cancelled)$")
    start_date: str | None = None
    due_date: str | None = None


class LabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, max_length=32)


class DependencyCreate(BaseModel):
    depends_on_task_id: int


class TaskUpdate(BaseModel):
    status: str | None = Field(default=None, min_length=1, max_length=40)
    priority: int | None = None
    assignee_user_id: str | None = None
    due_date: str | None = None
    estimate_minutes: int | None = Field(default=None, ge=0)
    position: int | None = None
    blocked: bool | None = None
    description: str | None = None
    milestone_id: int | None = None


@router.post("/milestones", status_code=201)
def create_milestone(item: MilestoneCreate, ctx=Depends(current_workspace)) -> dict:
    user, workspace_id = ctx
    with get_connection() as conn:
        if conn.execute(
            "SELECT 1 FROM projects WHERE id=%s AND workspace_id=%s",
            (item.project_id, workspace_id),
        ).fetchone() is None:
            raise HTTPException(404, "Project not found")
        row = conn.execute(
            """INSERT INTO milestones
               (workspace_id,project_id,name,description,status,start_date,due_date)
               VALUES(%s,%s,%s,%s,%s,%s,%s)
               RETURNING id,workspace_id,project_id,name,description,status,start_date,due_date,completed_at,created_at,updated_at""",
            (workspace_id,item.project_id,item.name,item.description,item.status,item.start_date,item.due_date),
        ).fetchone()
        conn.commit()
    return dict(row)


@router.get("/milestones")
def list_milestones(project_id: str | None = None, ctx=Depends(current_workspace)) -> list[dict]:
    user, workspace_id = ctx
    with get_connection() as conn:
        if project_id:
            rows = conn.execute(
                """SELECT id,workspace_id,project_id,name,description,status,start_date,due_date,completed_at,created_at,updated_at
                   FROM milestones WHERE workspace_id=%s AND project_id=%s ORDER BY due_date NULLS LAST,name""",
                (workspace_id, project_id),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id,workspace_id,project_id,name,description,status,start_date,due_date,completed_at,created_at,updated_at
                   FROM milestones WHERE workspace_id=%s ORDER BY due_date NULLS LAST,name""",
                (workspace_id,),
            ).fetchall()
    return [dict(row) for row in rows]


@router.post("/labels", status_code=201)
def create_label(item: LabelCreate, ctx=Depends(current_workspace)) -> dict:
    user, workspace_id = ctx
    with get_connection() as conn:
        try:
            row = conn.execute(
                "INSERT INTO labels(workspace_id,name,color) VALUES(%s,%s,%s) "
                "RETURNING id,workspace_id,name,color,created_at",
                (workspace_id,item.name,item.color),
            ).fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(409, "Label already exists") from exc
    return dict(row)


@router.get("/labels")
def list_labels(ctx=Depends(current_workspace)) -> list[dict]:
    user, workspace_id = ctx
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id,workspace_id,name,color,created_at FROM labels WHERE workspace_id=%s ORDER BY name",
            (workspace_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, item: TaskUpdate, ctx=Depends(current_workspace)) -> dict:
    user, workspace_id = ctx
    updates = item.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No task changes supplied")
    allowed = {
        "status", "priority", "assignee_user_id", "due_date",
        "estimate_minutes", "position", "blocked", "description", "milestone_id",
    }
    if set(updates) - allowed:
        raise HTTPException(422, "Unsupported task field")
    with get_connection() as conn:
        task = conn.execute(
            "SELECT id,project_id,milestone_id FROM tasks WHERE id=%s AND workspace_id=%s",
            (task_id, workspace_id),
        ).fetchone()
        if task is None:
            raise HTTPException(404, "Task not found")

        if "assignee_user_id" in updates and updates["assignee_user_id"]:
            if conn.execute(
                "SELECT 1 FROM workspace_members WHERE workspace_id=%s AND user_id=%s",
                (workspace_id, updates["assignee_user_id"]),
            ).fetchone() is None:
                raise HTTPException(400, "Assignee is not a member of this workspace")

        if "milestone_id" in updates and updates["milestone_id"] is not None:
            if conn.execute(
                "SELECT 1 FROM milestones WHERE id=%s AND workspace_id=%s AND project_id=%s",
                (updates["milestone_id"], workspace_id, task["project_id"]),
            ).fetchone() is None:
                raise HTTPException(400, "Milestone does not belong to this task's project")

        set_parts = []
        values = []
        for key, value in updates.items():
            set_parts.append(f"{key}=%s")
            values.append(value)

        if updates.get("status") == "completed":
            set_parts.append("completed_at=COALESCE(completed_at,NOW())")
        elif "status" in updates:
            set_parts.append("completed_at=NULL")

        set_parts.append("updated_at=NOW()")
        values.extend([task_id, workspace_id])

        row = conn.execute(
            f"""UPDATE tasks SET {", ".join(set_parts)}
                WHERE id=%s AND workspace_id=%s
                RETURNING id,project_id,conversation_id,title,status,priority,assignee_user_id,
                          due_date,started_at,completed_at,estimate_minutes,position,blocked,
                          description,milestone_id,provider,operation,arguments,command,context,created_at,updated_at""",
            tuple(values),
        ).fetchone()
        conn.commit()
    return dict(row)


@router.post("/tasks/{task_id}/dependencies", status_code=201)
def add_dependency(task_id: int, item: DependencyCreate, ctx=Depends(current_workspace)) -> dict:
    user, workspace_id = ctx
    if task_id == item.depends_on_task_id:
        raise HTTPException(400, "A task cannot depend on itself")
    with get_connection() as conn:
        if conn.execute(
            "SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s",
            (task_id, workspace_id),
        ).fetchone() is None:
            raise HTTPException(404, "Task not found")
        if conn.execute(
            "SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s",
            (item.depends_on_task_id, workspace_id),
        ).fetchone() is None:
            raise HTTPException(404, "Dependency task not found")
        try:
            row = conn.execute(
                """INSERT INTO task_dependencies(task_id,depends_on_task_id)
                   VALUES(%s,%s)
                   RETURNING task_id,depends_on_task_id,created_at""",
                (task_id,item.depends_on_task_id),
            ).fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(409, "Dependency already exists") from exc
    return dict(row)


@router.get("/tasks/{task_id}/dependencies")
def list_dependencies(task_id: int, ctx=Depends(current_workspace)) -> list[dict]:
    user, workspace_id = ctx
    with get_connection() as conn:
        if conn.execute(
            "SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s",
            (task_id, workspace_id),
        ).fetchone() is None:
            raise HTTPException(404, "Task not found")
        rows = conn.execute(
            """SELECT td.task_id,td.depends_on_task_id,td.created_at,t.title,t.status
               FROM task_dependencies td
               JOIN tasks t ON t.id=td.depends_on_task_id
               WHERE td.task_id=%s AND t.workspace_id=%s
               ORDER BY td.created_at""",
            (task_id, workspace_id),
        ).fetchall()
    return [dict(row) for row in rows]
