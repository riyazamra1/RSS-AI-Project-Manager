from fastapi import FastAPI

app = FastAPI(title="RSS AI Project Manager", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "rss-ai-project-manager"}


@app.get("/api/v1")
def api_info() -> dict[str, str]:
    return {"service": "RSS AI Project Manager API", "version": "v1"}
