from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.autopilot import Autopilot

router = APIRouter(prefix="/autopilot", tags=["autopilot"])


class ExecuteRequest(BaseModel):
    task: str = Field(min_length=1)
    context: str = ""


@router.post("/execute")
def execute(item: ExecuteRequest) -> dict[str, str]:
    try:
        result = Autopilot().execute(item.task, item.context)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "status": result.status,
        "provider": result.provider,
        "model": result.model,
        "output": result.output,
        "completed_at": result.completed_at,
    }
