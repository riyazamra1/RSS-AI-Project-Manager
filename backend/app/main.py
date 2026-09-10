from fastapi import FastAPI, HTTPException

from app.services.project_discovery import discover_projects

app = FastAPI(title="RSS AI Project Manager", version="0.2.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rss-ai-project-manager"}


@app.get("/api/v1")
def api_info() -> dict[str, str]:
    return {"service": "RSS AI Project Manager API", "version": "v1"}


@app.get("/api/v1/projects/discovery")
def project_discovery() -> dict:
    try:
        return discover_projects()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"GitHub discovery failed: {exc}") from exc
