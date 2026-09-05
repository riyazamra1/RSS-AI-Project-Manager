from fastapi import APIRouter

from ..db import get_connection

router = APIRouter(prefix="/status", tags=["status"])


@router.get("")
def status() -> dict:
    with get_connection() as conn:
        project_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        memory_count = conn.execute("SELECT COUNT(*) FROM project_memory").fetchone()[0]
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    return {
        "service": "rss-ai-project-manager",
        "database": "connected",
        "projects": project_count,
        "memory_records": memory_count,
        "tasks": task_count,
    }
