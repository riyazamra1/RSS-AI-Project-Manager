import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Request

from ..core.config import settings
from ..db import get_connection

router = APIRouter(prefix="/internal", tags=["internal"])

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _require_core(request: Request) -> None:
    expected = settings.rss_core_service_token.strip()
    supplied = request.headers.get("Authorization", "").replace("Bearer ", "", 1).strip()
    # RSS Core may deliver callbacks through an intermediary that does not
    # preserve the Authorization header. Accept the dedicated integration
    # header as a fallback while keeping the same shared secret.
    if not supplied:
        supplied = request.headers.get("X-RSS-Core-Service-Token", "").strip()
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(401, "RSS Core service authorization required")

async def _send_template(to: str, template_id: str, variables: dict[str, str]) -> None:
    if not settings.resend_api_key or not template_id:
        raise RuntimeError("Resend template email service is not configured")
    payload = {
        "from": settings.resend_from_email,
        "to": [to],
        "template": {"id": template_id, "variables": variables},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}", "Content-Type": "application/json"},
            json=payload,
        )
    if response.status_code >= 300:
        raise RuntimeError(f"Resend template send failed: {response.status_code}")

def _app_url(path: str = "") -> str:
    return settings.app_base_url.rstrip("/") + path

@router.post("/approval")
async def receive_core_approval(request: Request):
    _require_core(request)
    body = await request.json()
    request_id = str(body.get("request_id") or "").strip()
    user_id = str(body.get("user_id") or "").strip()
    status = str(body.get("status") or "").strip().lower()
    approved_by = str(body.get("approved_by") or "rss-core-admin").strip()
    if not request_id or not user_id or status not in {"approved", "rejected"}:
        raise HTTPException(400, "request_id, user_id and valid status are required")

    with get_connection() as conn:
        user = conn.execute(
            "SELECT id,email,full_name,approval_status FROM users WHERE id=%s AND approval_request_id=%s FOR UPDATE",
            (user_id, request_id),
        ).fetchone()
        if not user:
            raise HTTPException(404, "Project Manager account not found")
        conn.execute(
            """UPDATE users
               SET approval_status=%s,
                   approved_at=CASE WHEN %s='approved' THEN NOW() ELSE NULL END,
                   approved_by_external=%s,
                   updated_at=NOW()
               WHERE id=%s""",
            (status, status, approved_by, user_id),
        )
        if status == "approved":
            conn.execute(
                """UPDATE service_entitlements se SET enabled=TRUE,updated_at=NOW()
                   FROM workspaces w
                   WHERE se.workspace_id=w.id AND w.owner_user_id=%s AND se.service_key='project_manager'""",
                (user_id,),
            )
        else:
            conn.execute("UPDATE sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL", (user_id,))
        conn.commit()

    if status == "approved":
        try:
            await _send_template(
                user["email"],
                settings.resend_approval_template_id,
                {"USER_NAME": user["full_name"], "LOGIN_URL": _app_url("/")},
            )
            with get_connection() as conn:
                conn.execute("UPDATE users SET approval_email_sent_at=NOW(),approval_email_last_error=NULL WHERE id=%s", (user_id,))
                conn.commit()
        except Exception as exc:
            with get_connection() as conn:
                conn.execute("UPDATE users SET approval_email_last_error=%s WHERE id=%s", (str(exc)[:1000], user_id))
                conn.commit()
    return {"ok": True, "user_id": user_id, "request_id": request_id, "status": status}

@router.get("/health")
def internal_health(request: Request):
    _require_core(request)
    return {"ok": True, "service": "rss-ai-project-manager"}
