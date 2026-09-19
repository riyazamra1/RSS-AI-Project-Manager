-- RSS AI Project Manager: structured task execution contract for RSS Core/RAY
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS operation TEXT;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS arguments JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS command JSONB;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS context TEXT;

CREATE INDEX IF NOT EXISTS idx_tasks_status_created ON tasks(status, created_at);
