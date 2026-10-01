from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.ai import router as ai_router
from app.api.auto_chat import router as auto_chat_router
from app.api.auth import router as auth_router
from app.api.internal import router as internal_router
from app.api.conversations import router as conversations_router
from app.api.memory import router as memory_router
from app.api.project_discovery import router as project_discovery_router
from app.api.productivity import router as productivity_router
from app.api.projects import router as projects_router
from app.api.tasks import router as tasks_router
from app.services.project_chat_scheduler import ProjectChatScheduler


@asynccontextmanager
async def lifespan(app):
    scheduler = ProjectChatScheduler()
    await scheduler.start()
    app.state.project_chat_scheduler = scheduler
    try:
        yield
    finally:
        await scheduler.stop()


app = FastAPI(
    title="RSS AI Project Manager",
    version="0.9.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(internal_router)
app.include_router(projects_router, prefix="/api/v1")
app.include_router(project_discovery_router)
app.include_router(productivity_router, prefix="/api/v1")
app.include_router(memory_router, prefix="/api/v1")
app.include_router(conversations_router, prefix="/api/v1")
app.include_router(ai_router, prefix="/api/v1")
app.include_router(auto_chat_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "rss-ai-project-manager",
        "execution": "rss-core-cloudflare-ray",
    }


@app.get("/api/v1")
def api_info():
    return {
        "service": "RSS AI Project Manager API",
        "version": "v1",
        "execution_path": "rss-core-cloudflare-ray",
    }


# Resolve the web directory from the repository layout so CI, local runs,
# and the production container all use the same path without relying on /app.
WEB_DIR = Path(__file__).resolve().parents[2] / "web"
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
