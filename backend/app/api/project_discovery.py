from fastapi import APIRouter, HTTPException

from app.services.project_discovery import discover_projects

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.post("/discovery")
def run_project_discovery() -> dict:
    try:
        return discover_projects()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub discovery failed: {exc}") from exc
