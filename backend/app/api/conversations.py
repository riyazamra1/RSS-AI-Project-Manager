from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection

router = APIRouter(prefix="/conversations", tags=["conversations"])


class ConversationCreate(BaseModel):
    project_id: str | None = None
    title: str | None = Field(default=None, max_length=300)


class MessageCreate(BaseModel):
    role: str = Field(pattern="^(user|assistant|system|tool)$")
    content: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None


@router.post("", status_code=201)
def create_conversation(item: ConversationCreate) -> dict:
    with get_connection() as conn:
        if item.project_id:
            if conn.execute("SELECT 1 FROM projects WHERE id=%s", (item.project_id,)).fetchone() is None:
                raise HTTPException(status_code=404, detail="Project not found")
        row = conn.execute(
            "INSERT INTO conversations (project_id, title) VALUES (%s, %s) "
            "RETURNING id, project_id, title, created_at, updated_at",
            (item.project_id, item.title),
        ).fetchone()
        conn.commit()
    return dict(row)


@router.get("/{conversation_id}")
def get_conversation(conversation_id: int) -> dict:
    with get_connection() as conn:
        conversation = conn.execute(
            "SELECT id, project_id, title, created_at, updated_at FROM conversations WHERE id=%s",
            (conversation_id,),
        ).fetchone()
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        messages = conn.execute(
            "SELECT id, role, content, provider, model, created_at FROM messages "
            "WHERE conversation_id=%s ORDER BY created_at, id",
            (conversation_id,),
        ).fetchall()
    result = dict(conversation)
    result["messages"] = [dict(row) for row in messages]
    return result


@router.post("/{conversation_id}/messages", status_code=201)
def add_message(conversation_id: int, item: MessageCreate) -> dict:
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM conversations WHERE id=%s", (conversation_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        row = conn.execute(
            "INSERT INTO messages (conversation_id, role, content, provider, model) "
            "VALUES (%s, %s, %s, %s, %s) "
            "RETURNING id, conversation_id, role, content, provider, model, created_at",
            (conversation_id, item.role, item.content, item.provider, item.model),
        ).fetchone()
        conn.execute("UPDATE conversations SET updated_at=NOW() WHERE id=%s", (conversation_id,))
        conn.commit()
    return dict(row)
