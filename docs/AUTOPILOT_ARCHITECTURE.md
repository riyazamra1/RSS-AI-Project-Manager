# Internal Autopilot Engine Architecture

RSS Autopilot is an internal module of RSS AI Project Manager. It is not a second product.

```text
User task
  -> RSS AI Project Manager
  -> task/state storage
  -> RAY queue
  -> internal Autopilot engine
  -> Gemini / Codex-compatible worker
  -> target RSS repository
  -> build/test verification
  -> feature branch + pull request
  -> human review
```

## Boundaries
- Project Manager owns project state and user-facing status.
- RSS Core owns persistent shared storage and memory.
- RAY owns queued execution.
- Autopilot owns implementation orchestration and verification.
- AI workers are replaceable.
- Releases, destructive operations and irreversible changes remain gated by explicit approval.
