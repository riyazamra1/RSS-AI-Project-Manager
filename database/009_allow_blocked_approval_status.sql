-- RSS Core can suspend access by blocking a PM account. The account status constraint
-- must permit that state so the block operation can revoke sessions successfully.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_approval_status_check;
ALTER TABLE users ADD CONSTRAINT users_approval_status_check
  CHECK (approval_status IN ('pending','approved','rejected','suspended','blocked'));
