from fastapi import FastAPI

from app.api.project_discovery import router as project_discovery_router

app = FastAPI(title="RSS AI Project Manager", version="0.2.1")

app.include_router(project_discovery_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rss-ai-project-manager"}


@app.get("/api/v1")
def api_info() -> dict[str, str]:
    return {"service": "RSS AI Project Manager API", "version": "v1"}
