# RSS AI Project Manager

Central AI-powered project management and development control system for Razeen Secure Solution.

## Unified system

**RSS AI Project Manager is the single source of truth for project management and autonomous development.** The former RSS Autopilot is now an internal execution engine, not a separate application or repository.

### Internal modules
- Project Management — projects, requirements, tasks, decisions, status and activity history
- Autopilot Engine — AI-assisted implementation, build/test verification and GitHub PR automation
- RAY Queue — task execution and worker orchestration layer
- RSS Core — shared storage, memory and communication layer
- AI Workers — Gemini, OpenAI/Codex-compatible agents and future providers
- GitHub Automation — repository health, branches, commits and pull requests

## Core capabilities
- Unlimited project records
- Conversational AI interface
- Permanent project memory independent of chat-provider context
- Project status, tasks, requirements, decisions and activity history
- GitHub repository integration
- AI provider abstraction
- Cross-project automation through the internal Autopilot engine
- Self-hosted PostgreSQL and file/object storage
- Automatic memory updates after conversations and project actions
- Commands such as `All Status`, `Continue <Project>`, and project-specific updates

## Architecture

```text
User / Android / Web
        |
        v
RSS AI Project Manager
        |
   +----+-----------------------+
   |    |          |            |
Memory GitHub     RAY       Autopilot
   |               |            |
Storage       Task Queue    AI Workers
   |               |            |
   +---------------+------------+
                   |
              RSS Projects
```

The permanent project state belongs to RSS AI Project Manager/RSS Core. AI workers are replaceable execution components and never become a second source of truth.

## Repository policy

`riyazamra1/RSS-AI-Project-Manager` is the only active source-of-truth repository for this system. `RSS-Autopilot` and `RSS-Project-Autopilot` are legacy repositories and must not receive new development.

## Safety

No secrets, signing keys or production credentials are committed. Destructive actions, releases, deployments and irreversible repository operations require explicit user approval.
