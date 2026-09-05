# RSS AI Project Manager Backend

Self-hosted backend foundation for project registry, permanent memory, conversations, tasks, and activity history.

## Architecture

- PostgreSQL stores structured project state and permanent memory.
- Local/object storage can hold attachments and exported artifacts.
- API layer will expose project, memory, conversation, task, GitHub, and AI-router operations.
- AI providers remain behind the provider-independent router already documented in `docs/`.

## Planned runtime

Python + FastAPI + PostgreSQL. The backend is designed for deployment on the user's existing self-hosted infrastructure to minimize recurring infrastructure cost.
