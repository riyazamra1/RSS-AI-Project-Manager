-- RSS AI Project Manager account approval state.
-- RSS Core is the external approval authority; no RSS Core administrator is stored as a local users FK.
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved'
    CHECK (approval_status IN ('pending','approved','rejected','suspended')),
  ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approved_by_external TEXT;

-- Existing accounts remain usable after this migration.
UPDATE users
SET approval_status='approved',
    approved_at=COALESCE(approved_at, created_at)
WHERE approval_status IS NULL OR approval_status='approved';

CREATE INDEX IF NOT EXISTS idx_users_approval_status ON users(approval_status);
