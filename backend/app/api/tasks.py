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
    operation: str | None = Field(default=None, min_length=1, max_length=100)
    arguments: dict = Field(default_factory=dict)
    command: list[str] | None = None
    context: str | None = Field(default=None, max_length=12000)


def _validate_command(command: list[str] | None) -> list[str] | None:
    if command is None:
        return None
    if not command or len(command) > 32:
        raise HTTPException(status_code=422, detail="command must contain 1-32 arguments")
    if any(not isinstance(part, str) or not part.strip() or len(part) > 2048 for part in command):
        raise HTTPException(status_code=422, detail="command arguments must be non-empty strings <= 2048 characters")
    return command


@router.post("", status_code=201)
def create_task(item: TaskCreate) -> dict:
    command = _validate_command(item.command)
    with get_connection() as conn:
        if item.project_id and conn.execute("SELECT 1 FROM projects WHERE id=%s", (item.project_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if item.conversation_id and conn.execute("SELECT 1 FROM conversations WHERE id=%s", (item.conversation_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        row = conn.execute(
            "INSERT INTO tasks (project_id, conversation_id, title, provider, operation, arguments, command, context) "
            "VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s) "
            "RETURNING id, project_id, conversation_id, title, status, provider, operation, arguments, command, context, created_at, updated_at",
            (
                item.project_id,
                item.conversation_id,
                item.title,
                item.provider,
                item.operation,
                __import__("json").dumps(item.arguments),
                __import__("json").dumps(command) if command is not None else None,
                item.context,
            ),
        ).fetchone()
        conn.commit()
    return dict(row)


@router.get("")
def list_tasks(project_id: str | None = None) -> list[dict]:
    with get_connection() as conn:
        fields = "id, project_id, conversation_id, title, status, provider, operation, arguments, command, context, created_at, updated_at"
        if project_id:
            rows = conn.execute(
                f"SELECT {fields} FROM tasks WHERE project_id=%s ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        else:
            rows = conn.execute(f"SELECT {fields} FROM tasks ORDER BY created_at DESC").fetchall()
    return [dict(row) for row in rows]


@router.post("/run-next")
def run_next_task() -> dict:
    return TaskRunner().run_next()
