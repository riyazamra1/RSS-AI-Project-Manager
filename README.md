# RSS AI Project Manager

Central AI-powered project management and development control system for Razeen Secure Solution.

## Vision

Manage any number of projects through one conversational interface with permanent, self-hosted project memory.

## Core capabilities

- Unlimited project records (no hard-coded project-count limit)
- Conversational AI interface
- Permanent project memory stored independently of chat-provider context
- Project status, tasks, requirements, decisions, and activity history
- GitHub repository integration
- AI provider abstraction for Gemini, OpenAI/Codex-compatible agents, and future providers
- RSS Autopilot integration for cross-project automation
- Self-hosted PostgreSQL and file/object storage
- Automatic memory updates after conversations and project actions
- Commands such as `All Status`, `Continue <Project>`, and project-specific updates

## Architecture

The system is designed around a provider-independent memory layer. AI providers consume relevant project context; they do not own the project's permanent history.

```text
Android / Web Client
        |
        v
RSS AI Project Manager API
        |
   +----+----------------+
   |    |        |       |
Memory GitHub  Agents  Autopilot
   |             |
PostgreSQL   Gemini / Codex / future providers
   |
Self-hosted file storage
```

## Initial projects

The first tracked projects include the existing RSS projects and Razeen Secure Solution website. The system must support adding future projects without changing the architecture.

## Development principle

Preserve existing project context and continue from the latest known state. Internal conversation branches are implementation/history details and are not exposed as separate projects in the project dashboard.
