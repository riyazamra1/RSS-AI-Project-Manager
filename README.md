# RSS AI Project Manager

Central AI-powered project management and development control system for Razeen Secure Solution.

## Client applications

RSS AI Project Manager now has two full clients sharing the same backend/API:
- **Android:** native Kotlin/Jetpack Compose application, package `com.riyaz.rssaiprojectmanager`
- **Web:** backend/web control interface

Both clients use the same authenticated workspace state. Android can sign in, load projects, inspect tasks, create tasks, refresh project state, and request the next approved task through the authenticated backend execution endpoint. Privileged credentials remain server-side.

## PM portal feature map

The web client includes workspace overview and activity, project create/edit, task create/filter/status updates, persisted AI conversations, project memory for requirements and decisions, milestones, workspace labels, due-date calendar, automatic project check-in schedules, service status, and a command center for All Status, Continue, requirements, next, Go Ahead, and fix errors. Workspace-scoped requests include the X-Workspace-ID header. OAuth callbacks return the web session through a URL fragment that the browser consumes and removes.

The Cloudflare Workers static-portal deployment scaffold is in cloudflare-worker/. It is scoped to the portal HTML/JS/assets; FastAPI endpoints, PostgreSQL, email verification, RSS Core approval callbacks, and RAY execution remain on the existing backend. The Worker has not been deployed or live-verified merely by committing its configuration.

## Unified system

**RSS AI Project Manager is the single source of truth for project management and autonomous development.**

The execution model is **RSS Core + RAY + Cloudflare/worker orchestration**. The former RSS Autopilot is obsolete for this project and is **not an execution engine, fallback, or separate application**.

### Internal modules
- Project Management — projects, requirements, tasks, decisions, status and activity history
- RSS Core — shared storage, memory, authentication and communication/control-plane integration
- RAY Queue — the sole task execution and worker orchestration path
- AI Workers — Gemini, OpenAI/Codex-compatible agents and other approved providers behind RAY
- GitHub Integration — repository source-of-truth/context and controlled code operations

## Core capabilities
- Unlimited project records
- Conversational AI interface
- Permanent project memory independent of chat-provider context
- Project status, tasks, requirements, decisions and activity history
- GitHub repository integration
- AI provider abstraction
- Cross-project management without mixing project state
- Self-hosted PostgreSQL and file/object storage
- Automatic memory updates after conversations and project actions
- Commands such as `All Status`, `Continue <Project>`, and project-specific updates

## Execution architecture

```text
User / Android / Web
        |
        v
RSS AI Project Manager
        |
   +----+-----------------------+
   |    |          |            |
Memory GitHub   Task DB      RSS Core
   |    |          |             |
Storage |          v             v
        |        RAY Queue <-----+
        |          |
        |          v
        |    Cloudflare / Workers
        |          |
        |          v
        |     AI / OpenHands /
        |     Docker workers
        |          |
        +----------v
             RSS Projects
```

**Execution rule:** PM creates and tracks work; RSS Core/RAY executes it. PM must not execute AI work directly as a fallback. If RAY is unavailable or disabled, the task is blocked/retried and remains visible in PM state.

GitHub is the source of truth for project repositories, but GitHub Actions is **not required for runtime scheduling or execution**. Cloudflare/RSS Core/RAY is the intended runtime path because GitHub Actions limits must not block autonomous operation.

## RSS KIT authentication UI

The Android authentication surface uses the RSS KIT remote-auth contract. The native authentication engine remains local and secure, while public UI configuration is loaded from `/auth/ui-config` and cached on-device. Login/registration copy, logo URL, and supported visual tokens can therefore be updated server-side without reinstalling the APK. Native authentication logic or Android dependency changes still require an APK update.

## RSS requirements

This repository is also the control specification for RSS projects. Project requirements must be stored and applied per project without cross-project leakage. On project resume, the latest project requirements and repository state must be inspected before execution.

Global RSS KIT requirements include the standardized account/verification, RSS Core connection, cloud/multi-device sync, Premium entitlement behavior, and shared legal/about/contact surfaces, while each project keeps its own branding and UI.

## Project commands

Supported management concepts include:
- `All Status` — consolidated status across registered RSS projects without exposing branch names
- `Continue <Project>` — resume a specific project after inspecting its requirements and latest repository state
- `requirements` — show the project's stored requirements
- `next` — identify the next concrete project task
- `go ahead` — execute the next approved task through RSS Core/RAY
- `fix errors` — diagnose and repair the selected project's errors without changing other projects

## Repository policy

`riyazamra1/RSS-AI-Project-Manager` is the only active source-of-truth repository for this system. Legacy RSS Autopilot repositories must not receive new development.

## Verification policy

Repository implementation and production verification are separate states. A green repository change does not prove live Cloudflare/RSS Core/RAY execution. Production claims require actual runtime evidence.

## Safety

No secrets, signing keys or production credentials are committed. Destructive actions, releases, deployments and irreversible repository operations require explicit user approval.
