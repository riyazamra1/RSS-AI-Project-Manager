from fastapi import FastAPI

from app.api.ai import router as ai_router
from app.api.conversations import router as conversations_router
from app.api.memory import router as memory_router
from app.api.project_discovery import router as project_discovery_router
from app.api.projects import router as projects_router

app = FastAPI(title="RSS AI Project Manager", version="0.5.0")

app.include_router(projects_router, prefix="/api/v1")
app.include_router(project_discovery_router)
app.include_router(memory_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rss-ai-project-manager"}


@app.get("/api/v1")
def api_info() -> dict[str, str]:
    return {"service": "RSS AI Project Manager API", "version": "v1"}
