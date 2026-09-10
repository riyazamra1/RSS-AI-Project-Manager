from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..services.task_runner import TaskRunner

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=1000)
    project_id: str | None = None
    conversation_id: int | None = None
    provider: str | None = None


@router.post("", status_code=201)
def create_task(item: TaskCreate) -> dict:
    with get_connection() as conn:
        if item.project_id and conn.execute("SELECT 1 FROM projects WHERE id=%s", (item.project_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if item.conversation_id and conn.execute("SELECT 1 FROM conversations WHERE id=%s", (item.conversation_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        row = conn.execute(
            "INSERT INTO tasks (project_id, conversation_id, title, provider) VALUES (%s,%s,%s,%s) "
            "RETURNING id, project_id, conversation_id, title, status, provider, created_at, updated_at",
            (item.project_id, item.conversation_id, item.title, item.provider),
        ).fetchone()
        conn.commit()
    return dict(row)


@router.get("")
def list_tasks(project_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        if project_id:
            rows = conn.execute(
                "SELECT id, project_id, conversation_id, title, status, provider, created_at, updated_at "
                "FROM tasks WHERE project_id=%s ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, project_id, conversation_id, title, status, provider, created_at, updated_at "
                "FROM tasks ORDER BY created_at DESC"
            ).fetchall()
    return [dict(row) for row in rows]


@router.post("/run-next")
def run_next_task() -> dict:
    return TaskRunner().run_next()
