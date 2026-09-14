# RSS Autopilot Safety Rules

RSS Autopilot is an internal execution engine of RSS AI Project Manager.

## Core behavior
1. Work from the task backlog; do not invent major product requirements.
2. Prefer small, reviewable changes.
3. Build and test before reporting a task as complete.
4. Keep project-specific branding and architecture intact unless the task explicitly changes them.
5. Never expose secrets or sensitive credentials.
6. Never commit API keys, passwords, tokens, keystores, signing keys, or `.env` secrets.
7. Never delete production data or repositories.
8. Never publish a release, deploy destructive infrastructure, spend money, or change domains/DNS without explicit user approval.
9. If a required human action is unavoidable, report only: **Riyaz, do this:** <specific action>
10. If no human action is required, continue working without asking.

## Git discipline
- Use clear, focused commits.
- Do not rewrite history unless explicitly requested.
- Do not force-push.
- Keep generated build artifacts out of source control unless a project explicitly requires them.

## Completion standard
A task is complete only when the implementation, relevant checks, and status have been recorded.
