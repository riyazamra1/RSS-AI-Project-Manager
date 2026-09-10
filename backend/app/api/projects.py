from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..services.project_discovery import discover_projects

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    repository: str | None = None
    enabled: bool = True
    priority: int = 100


@router.get("")
def list_projects() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, name, repository, enabled, priority, created_at, updated_at "
            "FROM projects ORDER BY priority, name"
        ).fetchall()
    return list(rows)


@router.get("/{project_id}")
def get_project(project_id: str) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, repository, enabled, priority, created_at, updated_at "
            "FROM projects WHERE id = %s",
            (project_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


@router.post("", status_code=201)
def create_project(project: ProjectCreate) -> dict:
    with get_connection() as conn:
        try:
            row = conn.execute(
                "INSERT INTO projects (id, name, repository, enabled, priority) "
                "VALUES (%s, %s, %s, %s, %s) "
                "RETURNING id, name, repository, enabled, priority, created_at, updated_at",
                (project.id, project.name, project.repository, project.enabled, project.priority),
            ).fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(status_code=409, detail="Project ID already exists") from exc
    return row


@router.post("/sync")
def sync_projects() -> dict:
    try:
        result = discover_projects()
        with get_connection() as conn:
            for project in result["projects"]:
                conn.execute(
                    """
                    INSERT INTO projects (id, name, repository, enabled, priority)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        repository = EXCLUDED.repository,
                        enabled = EXCLUDED.enabled,
                        priority = EXCLUDED.priority,
                        updated_at = NOW()
                    """,
                    (
                        project["id"],
                        project["name"],
                        project.get("repository"),
                        project.get("enabled", True),
                        int(project.get("priority", 100)),
                    ),
                )
            conn.commit()
        return {"discovered": result["discovered"], "added": result["added"], "persisted": len(result["projects"])}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Project sync failed: {exc}") from exc
