-- Automatic project check-in/chat schedules.
CREATE TABLE IF NOT EXISTS project_chat_schedules (
    id BIGSERIAL PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    interval_minutes INTEGER NOT NULL CHECK (interval_minutes IN (15,20,30,60)),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_at TIMESTAMPTZ,
    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, project_id)
);
CREATE INDEX IF NOT EXISTS idx_project_chat_schedules_due ON project_chat_schedules(enabled,next_run_at);
CREATE INDEX IF NOT EXISTS idx_project_chat_schedules_workspace ON project_chat_schedules(workspace_id,project_id);
