# RSS AI Project Manager Backend

Self-hosted backend foundation for project registry, permanent memory, conversations, tasks, and activity history.

## Architecture

- PostgreSQL stores structured project state and permanent memory.
- Local/object storage can hold attachments and exported artifacts.
- API layer exposes project, memory, conversation, task, GitHub, and AI-router operations.
- AI providers remain behind the provider-independent router already documented in `docs/`.

## Dynamic project registry

The central registry is no longer limited to 13 projects. `config/projects.json` contains curated projects plus GitHub discovery rules for owner `riyazamra1`.

Discovery:
- includes repositories matching `RSS-*` and `RSS_*` plus the approved website repository;
- excludes known personal/legacy repositories;
- preserves curated metadata for existing projects;
- creates managed records for newly discovered repositories;
- has no hard-coded project-count limit;
- can be called through `GET /api/v1/projects/discovery`.

For authenticated GitHub access, set `RSS_GITHUB_TOKEN` (or `GITHUB_TOKEN`) in the backend environment. The token must have permission to read the repositories that should be managed.

## Planned runtime

Python + FastAPI + PostgreSQL. The backend is designed for deployment on the user's existing self-hosted infrastructure to minimize recurring infrastructure cost.
