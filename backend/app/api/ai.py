from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.ai_router import AIProviderRouter

router = APIRouter(prefix="/ai", tags=["ai"])


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)


@router.post("/generate")
def generate(item: GenerateRequest) -> dict[str, str]:
    try:
        result = AIProviderRouter().generate(item.prompt)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"provider": result.provider, "model": result.model, "content": result.content}
