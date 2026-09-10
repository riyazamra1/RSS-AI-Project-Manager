from fastapi import FastAPI

from app.api.projects import router as projects_router

app = FastAPI(title="RSS AI Project Manager", version="0.2.2")

app.include_router(projects_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rss-ai-project-manager"}


@app.get("/api/v1")
def api_info() -> dict[str, str]:
    return {"service": "RSS AI Project Manager API", "version": "v1"}
