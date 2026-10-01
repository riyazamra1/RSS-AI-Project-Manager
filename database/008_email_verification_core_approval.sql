-- RSS AI Project Manager: email verification + RSS Core approval bridge
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS approval_request_id UUID UNIQUE,
  ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approved_by_external TEXT,
  ADD COLUMN IF NOT EXISTS approval_email_sent_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approval_email_last_error TEXT;

CREATE TABLE IF NOT EXISTS email_verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_email_verifications_user ON email_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_email_verifications_expiry ON email_verifications(expires_at);
CREATE INDEX IF NOT EXISTS idx_users_approval_request ON users(approval_request_id);

-- Existing users are trusted legacy accounts; newly registered users remain pending.
UPDATE users SET email_verified_at=COALESCE(email_verified_at, created_at) WHERE email_verified=TRUE AND email_verified_at IS NULL;
