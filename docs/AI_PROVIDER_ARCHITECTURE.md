# AI Provider Architecture

## Goal

RSS AI Project Manager uses a provider-independent AI layer. The application must not be locked to one model or vendor.

## Provider priority

1. **Codex** — preferred for repository-level coding, debugging, refactoring, tests, and implementation tasks when available.
2. **Gemini** — free-first fallback and general AI provider when Codex is unavailable or its allowance is exhausted.
3. **Future providers** — the interface is intentionally extensible for additional hosted or local models.

## Routing rules

The AI router receives a normalized task:

- project ID
- task type
- user instruction
- relevant project memory
- relevant conversation context
- repository context when needed
- requested actions/tools

The router selects a provider without exposing provider-specific complexity to the Android client.

### Preferred behavior

```text
User request
    ↓
Project identification
    ↓
Load permanent memory + current state
    ↓
AI Provider Router
    ↓
Codex available? ── yes → Codex
    │
    no
    ↓
Gemini available? ── yes → Gemini
    │
    no
    ↓
Return actionable provider-unavailable state
```

The router must never silently pretend that an unavailable provider completed work.

## Configuration

Credentials are supplied only through server-side environment variables or a secret manager. Never commit API keys, OAuth tokens, or personal credentials to GitHub.

Suggested configuration:

```text
AI_PRIMARY_PROVIDER=codex
AI_FALLBACK_PROVIDER=gemini
CODEX_API_KEY=<server secret>
GEMINI_API_KEY=<server secret>
GEMINI_MODEL=<configured model>
```

The exact Codex authentication mechanism can vary depending on deployment, so the provider adapter must isolate authentication details from the rest of the application.

## Provider interface

Every provider should implement the same logical operations:

- `chat()` — normal conversational response
- `plan()` — produce an implementation plan
- `code()` — generate or modify code through approved tools
- `review()` — inspect code and report issues
- `summarize()` — compress project activity into durable memory
- `status()` — report provider availability and quota state

## Cost policy

The application is designed as **free-first**, not as a promise of unlimited free inference. Provider quotas, plan allowances, and pricing can change. Infrastructure should remain self-hosted where practical so AI usage is the main variable cost.

## Security

- API keys stay on the backend.
- The Android client never receives provider secrets.
- Provider requests should be logged with metadata, not secret values.
- Conversation and project data should be scoped by authenticated user/project permissions.
- GitHub write operations require explicit application authorization and should be auditable.
