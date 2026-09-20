from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..security import current_workspace

router = APIRouter(prefix="/conversations", tags=["conversations"])

class ConversationCreate(BaseModel):
    project_id: str | None = None
    title: str | None = Field(default=None, max_length=300)

class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant|system|tool)$")
    content: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None

def _conversation_workspace(conn, conversation_id: int, workspace_id: str):
    row = conn.execute(
        "SELECT id,project_id,title,created_at,updated_at FROM conversations WHERE id=%s AND workspace_id=%s",
        (conversation_id, workspace_id),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Conversation not found")
    return row

@router.post("", status_code=201)
def create_conversation(item: ConversationCreate, ctx: dict = Depends(current_workspace)) -> dict:
    with get_connection() as conn:
        if item.project_id and conn.execute("SELECT 1 FROM projects WHERE id=%s AND workspace_id=%s", (item.project_id, ctx["workspace_id"])).fetchone() is None:
            raise HTTPException(404, "Project not found")
        row = conn.execute(
            "INSERT INTO conversations (project_id,workspace_id,title) VALUES (%s,%s,%s) RETURNING id,project_id,title,created_at,updated_at",
            (item.project_id, ctx["workspace_id"], item.title),
        ).fetchone()
        conn.commit()
    return dict(row)

@router.get("/{conversation_id}")
def get_conversation(conversation_id: int, ctx: dict = Depends(current_workspace)) -> dict:
    with get_connection() as conn:
        conversation = _conversation_workspace(conn, conversation_id, ctx["workspace_id"])
        messages = conn.execute(
            "SELECT id,role,content,provider,model,created_at FROM messages WHERE conversation_id=%s ORDER BY created_at,id",
            (conversation_id,),
        ).fetchall()
    result = dict(conversation)
    result["messages"] = [dict(row) for row in messages]
    return result

@router.post("/{conversation_id}/messages", status_code=201)
def add_message(conversation_id: int, item: MessageCreate, ctx: dict = Depends(current_workspace)) -> dict:
    with get_connection() as conn:
        _conversation_workspace(conn, conversation_id, ctx["workspace_id"])
        row = conn.execute(
            "INSERT INTO messages (conversation_id,role,content,provider,model) VALUES (%s,%s,%s,%s,%s) RETURNING id,conversation_id,role,content,provider,model,created_at",
            (conversation_id, item.role, item.content, item.provider, item.model),
        ).fetchone()
        conn.execute("UPDATE conversations SET updated_at=NOW() WHERE id=%s AND workspace_id=%s", (conversation_id, ctx["workspace_id"]))
        conn.commit()
    return dict(row)
