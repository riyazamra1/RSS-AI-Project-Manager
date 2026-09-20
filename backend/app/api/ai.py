from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..security import current_workspace, service_access
from ..services.ai_router import AIProviderRouter

router = APIRouter(prefix="/ai", tags=["ai"])

class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)

@router.post("/generate")
def generate(item: GenerateRequest, ctx: dict = Depends(current_workspace)) -> dict[str, str]:
    service_access(ctx["user"], ctx["workspace_id"], "project_manager")
    try:
        result = AIProviderRouter().generate(item.prompt)
    except Exception as exc:
        raise HTTPException(503, "AI provider unavailable") from exc
    return {"provider": result.provider, "model": result.model, "content": result.content}
