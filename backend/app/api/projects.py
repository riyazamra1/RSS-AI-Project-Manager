from fastapi import APIRouter, Depends, HTTPException
import json
from pathlib import Path
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

class ProjectUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    repository: str | None = None
    enabled: bool = True
    priority: int = 100
    description: str | None = Field(default=None, max_length=5000)

def _import_registry_into_workspace(workspace_id: str) -> dict:
    """Idempotently populate an empty workspace with the configured RSS portfolio."""
    registry_path = Path(__file__).resolve().parents[3] / "config" / "projects.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        configured = registry.get("projects", [])
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "RSS project registry is unavailable") from exc
    imported = 0
    skipped = 0
    suffix = workspace_id.replace("-", "")[:10]
    with get_connection() as conn:
        existing = conn.execute("SELECT repository FROM projects WHERE workspace_id=%s AND repository IS NOT NULL", (workspace_id,)).fetchall()
        existing_repositories = {str(row["repository"]).lower() for row in existing if row["repository"]}
        for item in configured:
            canonical_id = str(item.get("id", "")).strip()
            name = str(item.get("name", "")).strip()
            if not canonical_id or not name:
                continue
            repository = item.get("repository")
            if repository and str(repository).lower() in existing_repositories:
                skipped += 1
                continue
            project_id = f"{canonical_id[:105]}-{suffix}"
            row = conn.execute(
                """INSERT INTO projects(id,name,repository,enabled,priority,description,workspace_id)
                   VALUES(%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(id) DO NOTHING RETURNING id""",
                (project_id, name, repository, bool(item.get("enabled", True)),
                 int(item.get("priority", 100)), item.get("description"), workspace_id),
            ).fetchone()
            if row:
                imported += 1
                if repository:
                    existing_repositories.add(str(repository).lower())
            else:
                skipped += 1
        conn.commit()
    return {"imported": imported, "skipped": skipped, "workspace_id": workspace_id}

@router.get("")
def list_projects(ctx: dict = Depends(current_workspace)) -> list[dict]:
    workspace_id = str(ctx["workspace_id"])
    with get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) AS total FROM projects WHERE workspace_id=%s", (workspace_id,)).fetchone()
    # Existing accounts should see the RSS portfolio automatically; do not require a separate create/import action.
    if not count or int(count["total"]) == 0:
        _import_registry_into_workspace(workspace_id)
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT id,name,repository,enabled,priority,description,status,start_date,due_date,archived,created_at,updated_at
               FROM projects WHERE workspace_id=%s ORDER BY priority,name""",
            (workspace_id,),
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
def update_project(project_id: str, project: ProjectUpdate, ctx: dict = Depends(require_workspace_role("manager"))) -> dict:
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

@router.post("/import-registry")
def import_registry_projects(ctx: dict = Depends(require_workspace_role("manager"))) -> dict:
    """Manually re-import registry projects that are missing from the current workspace."""
    result = _import_registry_into_workspace(str(ctx["workspace_id"]))
    audit(ctx["user"], ctx["workspace_id"], "project.registry_import", "workspace", str(ctx["workspace_id"]), result)
    return result

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
