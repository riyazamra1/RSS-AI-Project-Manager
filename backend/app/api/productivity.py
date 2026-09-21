from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..security import require_auth, workspace_access, audit

router = APIRouter(prefix="/pm", tags=["productivity"])


def current_workspace(
    workspace_id: str | None = Header(default=None, alias="X-Workspace-ID"),
    user: dict = Depends(require_auth),
) -> tuple[dict, str]:
    if not workspace_id:
        raise HTTPException(400, "X-Workspace-ID is required")
    workspace_access(user, workspace_id, "viewer")
    return user, workspace_id


def require_pm_editor(ctx=Depends(current_workspace)):
    user, workspace_id = ctx
    workspace_access(user, workspace_id, "developer")
    return ctx


class MilestoneCreate(BaseModel):
    project_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: str = Field(default="planned", pattern="^(planned|active|completed|cancelled)$")
    start_date: str | None = None
    due_date: str | None = None


class LabelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, max_length=32)


class DependencyCreate(BaseModel):
    depends_on_task_id: int


class TaskLabelCreate(BaseModel):
    label_id: int


class TaskUpdate(BaseModel):
    status: str | None = Field(default=None, min_length=1, max_length=40)
    priority: int | None = None
    assignee_user_id: str | None = None
    due_date: str | None = None
    estimate_minutes: int | None = Field(default=None, ge=0)
    position: int | None = None
    blocked: bool | None = None
    description: str | None = Field(default=None, max_length=12000)
    milestone_id: int | None = None


@router.post("/milestones", status_code=201)
def create_milestone(item: MilestoneCreate, ctx=Depends(require_pm_editor)) -> dict:
    user, workspace_id = ctx
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM projects WHERE id=%s AND workspace_id=%s", (item.project_id, workspace_id)).fetchone() is None:
            raise HTTPException(404, "Project not found")
        row = conn.execute(
            """INSERT INTO milestones(workspace_id,project_id,name,description,status,start_date,due_date)
               VALUES(%s,%s,%s,%s,%s,%s,%s)
               RETURNING id,workspace_id,project_id,name,description,status,start_date,due_date,completed_at,created_at,updated_at""",
            (workspace_id,item.project_id,item.name,item.description,item.status,item.start_date,item.due_date),
        ).fetchone()
        conn.commit()
    audit(user, workspace_id, "milestone.create", "milestone", str(row["id"]))
    return dict(row)


@router.get("/milestones")
def list_milestones(project_id: str | None = None, ctx=Depends(current_workspace)) -> list[dict]:
    _, workspace_id = ctx
    with get_connection() as conn:
        if project_id and conn.execute("SELECT 1 FROM projects WHERE id=%s AND workspace_id=%s", (project_id, workspace_id)).fetchone() is None:
            raise HTTPException(404, "Project not found")
        query = "SELECT id,workspace_id,project_id,name,description,status,start_date,due_date,completed_at,created_at,updated_at FROM milestones WHERE workspace_id=%s"
        args = [workspace_id]
        if project_id:
            query += " AND project_id=%s"
            args.append(project_id)
        rows = conn.execute(query + " ORDER BY due_date NULLS LAST,name", tuple(args)).fetchall()
    return [dict(row) for row in rows]


@router.post("/labels", status_code=201)
def create_label(item: LabelCreate, ctx=Depends(require_pm_editor)) -> dict:
    user, workspace_id = ctx
    with get_connection() as conn:
        try:
            row = conn.execute("INSERT INTO labels(workspace_id,name,color) VALUES(%s,%s,%s) RETURNING id,workspace_id,name,color,created_at", (workspace_id,item.name.strip(),item.color)).fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(409, "Label already exists") from exc
    audit(user, workspace_id, "label.create", "label", str(row["id"]))
    return dict(row)


@router.get("/labels")
def list_labels(ctx=Depends(current_workspace)) -> list[dict]:
    _, workspace_id = ctx
    with get_connection() as conn:
        rows = conn.execute("SELECT id,workspace_id,name,color,created_at FROM labels WHERE workspace_id=%s ORDER BY name", (workspace_id,)).fetchall()
    return [dict(row) for row in rows]


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, item: TaskUpdate, ctx=Depends(require_pm_editor)) -> dict:
    user, workspace_id = ctx
    updates = item.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "No task changes supplied")
    with get_connection() as conn:
        task = conn.execute("SELECT id,project_id FROM tasks WHERE id=%s AND workspace_id=%s", (task_id,workspace_id)).fetchone()
        if task is None:
            raise HTTPException(404, "Task not found")
        if "assignee_user_id" in updates and updates["assignee_user_id"] and conn.execute("SELECT 1 FROM workspace_members WHERE workspace_id=%s AND user_id=%s", (workspace_id,updates["assignee_user_id"])).fetchone() is None:
            raise HTTPException(400, "Assignee is not a member of this workspace")
        if updates.get("milestone_id") is not None and conn.execute("SELECT 1 FROM milestones WHERE id=%s AND workspace_id=%s AND project_id=%s", (updates["milestone_id"],workspace_id,task["project_id"])).fetchone() is None:
            raise HTTPException(400, "Milestone does not belong to this task's project")
        sets=[]; values=[]
        for key,value in updates.items():
            sets.append(f"{key}=%s"); values.append(value)
        if updates.get("status") == "completed": sets.append("completed_at=COALESCE(completed_at,NOW())")
        elif "status" in updates: sets.append("completed_at=NULL")
        sets.append("updated_at=NOW()"); values.extend([task_id,workspace_id])
        row=conn.execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=%s AND workspace_id=%s RETURNING id,project_id,conversation_id,title,status,priority,assignee_user_id,due_date,started_at,completed_at,estimate_minutes,position,blocked,description,milestone_id,provider,operation,arguments,command,context,created_at,updated_at",tuple(values)).fetchone()
        conn.commit()
    audit(user, workspace_id, "task.update", "task", str(task_id), {"fields": sorted(updates.keys())})
    return dict(row)


@router.post("/tasks/{task_id}/labels", status_code=201)
def attach_task_label(task_id: int, item: TaskLabelCreate, ctx=Depends(require_pm_editor)) -> dict:
    user, workspace_id = ctx
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s", (task_id,workspace_id)).fetchone() is None:
            raise HTTPException(404, "Task not found")
        if conn.execute("SELECT 1 FROM labels WHERE id=%s AND workspace_id=%s", (item.label_id,workspace_id)).fetchone() is None:
            raise HTTPException(404, "Label not found")
        try:
            conn.execute("INSERT INTO task_labels(task_id,label_id) VALUES(%s,%s)", (task_id,item.label_id))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(409, "Label already attached") from exc
    audit(user, workspace_id, "task.label.attach", "task", str(task_id), {"label_id": item.label_id})
    return {"task_id": task_id, "label_id": item.label_id}


@router.delete("/tasks/{task_id}/labels/{label_id}")
def detach_task_label(task_id: int, label_id: int, ctx=Depends(require_pm_editor)) -> dict:
    user, workspace_id = ctx
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s", (task_id,workspace_id)).fetchone() is None:
            raise HTTPException(404, "Task not found")
        conn.execute("DELETE FROM task_labels WHERE task_id=%s AND label_id=%s AND EXISTS (SELECT 1 FROM labels WHERE id=%s AND workspace_id=%s)", (task_id,label_id,label_id,workspace_id))
        conn.commit()
    audit(user, workspace_id, "task.label.detach", "task", str(task_id), {"label_id": label_id})
    return {"task_id": task_id, "label_id": label_id, "detached": True}


@router.get("/tasks/{task_id}/labels")
def list_task_labels(task_id: int, ctx=Depends(current_workspace)) -> list[dict]:
    _, workspace_id = ctx
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s", (task_id,workspace_id)).fetchone() is None:
            raise HTTPException(404, "Task not found")
        rows=conn.execute("SELECT l.id,l.name,l.color FROM task_labels tl JOIN labels l ON l.id=tl.label_id WHERE tl.task_id=%s AND l.workspace_id=%s ORDER BY l.name", (task_id,workspace_id)).fetchall()
    return [dict(row) for row in rows]


@router.post("/tasks/{task_id}/dependencies", status_code=201)
def add_dependency(task_id: int, item: DependencyCreate, ctx=Depends(require_pm_editor)) -> dict:
    user, workspace_id = ctx
    if task_id == item.depends_on_task_id:
        raise HTTPException(400, "A task cannot depend on itself")
    with get_connection() as conn:
        for candidate in (task_id,item.depends_on_task_id):
            if conn.execute("SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s", (candidate,workspace_id)).fetchone() is None:
                raise HTTPException(404, "Task not found in this workspace")
        try:
            row=conn.execute("INSERT INTO task_dependencies(task_id,depends_on_task_id) VALUES(%s,%s) RETURNING task_id,depends_on_task_id,created_at", (task_id,item.depends_on_task_id)).fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback(); raise HTTPException(409, "Dependency already exists") from exc
    audit(user, workspace_id, "task.dependency.add", "task", str(task_id), {"depends_on_task_id": item.depends_on_task_id})
    return dict(row)


@router.get("/tasks/{task_id}/dependencies")
def list_dependencies(task_id: int, ctx=Depends(current_workspace)) -> list[dict]:
    _, workspace_id = ctx
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM tasks WHERE id=%s AND workspace_id=%s", (task_id,workspace_id)).fetchone() is None:
            raise HTTPException(404, "Task not found")
        rows=conn.execute("SELECT td.task_id,td.depends_on_task_id,td.created_at,t.title,t.status FROM task_dependencies td JOIN tasks t ON t.id=td.depends_on_task_id WHERE td.task_id=%s AND t.workspace_id=%s ORDER BY td.created_at", (task_id,workspace_id)).fetchall()
    return [dict(row) for row in rows]



@router.get("/dashboard")
def dashboard_metrics(ctx=Depends(current_workspace)) -> dict:
    _, workspace_id = ctx
    with get_connection() as conn:
        projects = conn.execute(
            """SELECT
                 COUNT(*)::int AS total,
                 COUNT(*) FILTER (WHERE archived=false)::int AS active,
                 COUNT(*) FILTER (WHERE status='completed')::int AS completed
               FROM projects WHERE workspace_id=%s""",
            (workspace_id,),
        ).fetchone()
        tasks = conn.execute(
            """SELECT
                 COUNT(*)::int AS total,
                 COUNT(*) FILTER (WHERE status='pending')::int AS pending,
                 COUNT(*) FILTER (WHERE status='running')::int AS running,
                 COUNT(*) FILTER (WHERE status='completed')::int AS completed,
                 COUNT(*) FILTER (WHERE status='failed')::int AS failed,
                 COUNT(*) FILTER (WHERE blocked=true AND status NOT IN ('completed','failed'))::int AS blocked,
                 COUNT(*) FILTER (WHERE due_date < CURRENT_DATE AND status NOT IN ('completed','failed'))::int AS overdue
               FROM tasks WHERE workspace_id=%s""",
            (workspace_id,),
        ).fetchone()
        milestones = conn.execute(
            """SELECT
                 COUNT(*)::int AS total,
                 COUNT(*) FILTER (WHERE status='completed')::int AS completed,
                 COUNT(*) FILTER (WHERE due_date < CURRENT_DATE AND status <> 'completed')::int AS overdue
               FROM milestones WHERE workspace_id=%s""",
            (workspace_id,),
        ).fetchone()
        activity = conn.execute(
            """SELECT event_type,summary,created_at
               FROM activity_log WHERE workspace_id=%s
               ORDER BY created_at DESC LIMIT 10""",
            (workspace_id,),
        ).fetchall()
    return {
        "projects": dict(projects),
        "tasks": dict(tasks),
        "milestones": dict(milestones),
        "recent_activity": [dict(row) for row in activity],
    }


@router.get("/calendar/tasks")
def calendar_tasks(
    start_date: str | None = None,
    end_date: str | None = None,
    ctx=Depends(current_workspace),
) -> list[dict]:
    _, workspace_id = ctx
    with get_connection() as conn:
        query = """SELECT id,project_id,title,status,priority,assignee_user_id,due_date,
                          started_at,completed_at,estimate_minutes,position,blocked,milestone_id
                   FROM tasks WHERE workspace_id=%s"""
        args: list = [workspace_id]
        if start_date:
            query += " AND COALESCE(due_date, started_at::date) >= %s"
            args.append(start_date)
        if end_date:
            query += " AND COALESCE(due_date, started_at::date) <= %s"
            args.append(end_date)
        rows = conn.execute(query + " ORDER BY COALESCE(due_date, started_at::date), position NULLS LAST, id", tuple(args)).fetchall()
    return [dict(row) for row in rows]
