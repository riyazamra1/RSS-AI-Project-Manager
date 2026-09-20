from fastapi import APIRouter, Depends, HTTPException

from app.services.project_discovery import discover_projects
from app.security import require_worker

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("/discovery")
def run_project_discovery(_: bool = Depends(require_worker)) -> dict:
    try:
        return discover_projects()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub discovery failed: {exc}") from exc
