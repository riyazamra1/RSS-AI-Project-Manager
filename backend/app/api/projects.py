from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection
from ..services.project_discovery import discover_projects
from ..security import current_workspace, require_workspace_role, require_worker, audit

router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectCreate(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    repository: str | None = None
    enabled: bool = True
    priority: int = 100
    description: str | None = Field(default=None, max_length=5000)

@router.get("")
def list_projects(ctx: dict = Depends(current_workspace)) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,name,repository,enabled,priority,description,status,start_date,due_date,archived,created_at,updated_at
               FROM projects WHERE workspace_id=%s ORDER BY priority,name""",
            (ctx["workspace_id"],),
        ).fetchall()
    return list(rows)

@router.get("/{project_id}")
def get_project(project_id: str, ctx: dict = Depends(current_workspace)) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id,name,repository,enabled,priority,description,status,start_date,due_date,archived,created_at,updated_at
               FROM projects WHERE id=%s AND workspace_id=%s""",
            (project_id, ctx["workspace_id"]),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Project not found")
    return dict(row)

@router.post("", status_code=201)
def create_project(project: ProjectCreate, ctx: dict = Depends(require_workspace_role("manager"))) -> dict:
    with get_connection() as conn:
        try:
            row = conn.execute(
                """INSERT INTO projects(id,name,repository,enabled,priority,description,workspace_id)
                   VALUES(%s,%s,%s,%s,%s,%s,%s)
                   RETURNING id,name,repository,enabled,priority,description,status,start_date,due_date,archived,created_at,updated_at""",
                (project.id,project.name,project.repository,project.enabled,project.priority,project.description,ctx["workspace_id"]),
            ).fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(409, "Project ID already exists") from exc
    audit(ctx["user"],ctx["workspace_id"],"project.create","project",project.id)
    return dict(row)

@router.patch("/{project_id}")
def update_project(project_id: str, project: ProjectCreate, ctx: dict = Depends(require_workspace_role("manager"))) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            """UPDATE projects SET name=%s,repository=%s,enabled=%s,priority=%s,description=%s,updated_at=NOW()
               WHERE id=%s AND workspace_id=%s
               RETURNING id,name,repository,enabled,priority,description,status,start_date,due_date,archived,created_at,updated_at""",
            (project.name,project.repository,project.enabled,project.priority,project.description,project_id,ctx["workspace_id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Project not found")
        conn.commit()
    audit(ctx["user"],ctx["workspace_id"],"project.update","project",project_id)
    return dict(row)

@router.post("/sync")
def sync_projects(_: bool = Depends(require_worker)) -> dict:
    try:
        result = discover_projects()
        with get_connection() as conn:
            for project in result["projects"]:
                conn.execute(
                    """INSERT INTO projects(id,name,repository,enabled,priority,workspace_id)
                       VALUES(%s,%s,%s,%s,%s,'00000000-0000-0000-0000-000000000001')
                       ON CONFLICT(id) DO UPDATE SET
                         name=EXCLUDED.name,repository=EXCLUDED.repository,
                         enabled=EXCLUDED.enabled,priority=EXCLUDED.priority,updated_at=NOW()""",
                    (project["id"],project["name"],project.get("repository"),project.get("enabled",True),int(project.get("priority",100))),
                )
            conn.commit()
        return {"discovered":result["discovered"],"added":result["added"],"persisted":len(result["projects"])}
    except Exception as exc:
        raise HTTPException(503,"Project sync failed") from exc
