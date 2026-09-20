from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..security import current_workspace, service_access, audit
from ..services.autopilot import Autopilot

router = APIRouter(prefix="/autopilot", tags=["autopilot"])

class ExecuteRequest(BaseModel):
    task: str = Field(min_length=1, max_length=12000)
    context: str = Field(default="", max_length=12000)

@router.post("/execute")
def execute(item: ExecuteRequest, ctx: dict = Depends(current_workspace)) -> dict[str, str]:
    service_access(ctx["user"], ctx["workspace_id"], "project_manager")
    try:
        result = Autopilot().execute(item.task, item.context)
    except Exception as exc:
        raise HTTPException(503, "Autopilot unavailable") from exc
    audit(ctx["user"],ctx["workspace_id"],"autopilot.execute")
    return {"status":result.status,"provider":result.provider,"model":result.model,"output":result.output,"completed_at":result.completed_at}
