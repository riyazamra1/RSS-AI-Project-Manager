# AI Router Task Policy

RSS AI Project Manager should route work by task type while keeping one conversational experience.

| Task | Preferred provider | Fallback |
|---|---|---|
| Repository coding | Codex | Gemini |
| Debugging | Codex | Gemini |
| Refactoring | Codex | Gemini |
| Code review | Codex | Gemini |
| Architecture planning | Codex | Gemini |
| Project status | Gemini | Codex |
| Requirements / planning conversation | Gemini | Codex |
| Memory summarization | Gemini | Codex |
| General assistant chat | Gemini | Codex |

## Important behavior

Provider selection is an implementation detail. The user should continue talking to RSS AI Project Manager normally; they should not have to manually choose an AI for routine work.

When a coding request needs GitHub changes, the router should attach repository context and use the coding provider. When the request is primarily project-management conversation, use the general provider first.

If the selected provider fails because of quota, availability, authentication, or a transient error, the router should attempt the configured fallback where the task is safe to continue. The resulting response must identify that a fallback was used when this is relevant to auditability.

All provider calls should record:

- project ID
- task ID when available
- provider
- model
- request type
- start/end timestamps
- success/failure
- fallback reason when applicable

Do not store API keys or full secret-bearing request headers in logs.
