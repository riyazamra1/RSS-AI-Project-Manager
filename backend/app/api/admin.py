from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from ..db import get_connection
from ..security import require_platform_admin

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/pending-users")
def pending_users(admin: dict = Depends(require_platform_admin)):
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT u.id,u.email,u.full_name,u.created_at,
                      COALESCE(string_agg(w.name, ', ' ORDER BY w.name), '') AS workspaces
               FROM users u
               LEFT JOIN workspaces w ON w.owner_user_id=u.id
               WHERE u.approval_status='pending'
               GROUP BY u.id
               ORDER BY u.created_at ASC"""
        ).fetchall()
    return {"users": [dict(row) for row in rows]}

@router.post("/users/{user_id}/approve")
def approve_user(user_id: UUID, admin: dict = Depends(require_platform_admin)):
    with get_connection() as conn:
        user = conn.execute("SELECT id,approval_status FROM users WHERE id=%s FOR UPDATE", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        conn.execute(
            """UPDATE users
               SET approval_status='approved',approved_at=NOW(),approved_by=%s,updated_at=NOW()
               WHERE id=%s""",
            (admin["id"], user_id),
        )
        conn.execute(
            """UPDATE service_entitlements se
               SET enabled=TRUE,updated_at=NOW()
               FROM workspaces w
               WHERE se.workspace_id=w.id AND w.owner_user_id=%s AND se.service_key='project_manager'""",
            (user_id,),
        )
        conn.commit()
    return {"status": "approved", "user_id": str(user_id)}

@router.post("/users/{user_id}/reject")
def reject_user(user_id: UUID, admin: dict = Depends(require_platform_admin)):
    with get_connection() as conn:
        user = conn.execute("SELECT id FROM users WHERE id=%s", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "User not found")
        conn.execute(
            """UPDATE users
               SET approval_status='rejected',approved_at=NULL,approved_by=%s,updated_at=NOW()
               WHERE id=%s""",
            (admin["id"], user_id),
        )
        conn.execute("UPDATE sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
        conn.commit()
    return {"status": "rejected", "user_id": str(user_id)}
