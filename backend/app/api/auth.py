import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID, uuid4

from ..core.config import settings
from ..db import get_connection
from ..security import create_session, hash_password, require_auth, require_platform_admin, revoke_session, user_workspaces, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=200)
    password: str = Field(min_length=12, max_length=200)
    workspace_name: str = Field(min_length=2, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)

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

async def _submit_to_rss_core(user_id: str, request_id: str, email: str, full_name: str) -> None:
    url = settings.rss_core_approval_url.rstrip("/") + "/api/v1/internal/project-manager/registration-requests"
    if not settings.rss_core_service_token or not settings.rss_core_approval_url:
        raise RuntimeError("RSS Core approval bridge is not configured")
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {settings.rss_core_service_token}", "Content-Type": "application/json"},
            json={"request_id": request_id, "user_id": user_id, "email": email, "name": full_name},
        )
    if response.status_code >= 300:
        raise RuntimeError(f"RSS Core approval request failed: {response.status_code}")


def _oauth_config(provider: str) -> tuple[str, str, str]:
    if provider == "google":
        return (
            settings.google_client_id,
            settings.google_client_secret,
            "https://accounts.google.com/o/oauth2/v2/auth",
        )
    if provider == "github":
        return (
            settings.github_oauth_client_id,
            settings.github_oauth_client_secret,
            "https://github.com/login/oauth/authorize",
        )
    raise HTTPException(404, "Unsupported OAuth provider")


def _redirect_uri(provider: str) -> str:
    base = settings.oauth_redirect_base_url.rstrip("/")
    if not base or not base.startswith("https://"):
        raise HTTPException(503, "OAuth redirect base URL is not configured with HTTPS")
    return f"{base}/auth/{provider}/callback"


def _new_state(provider: str) -> str:
    state = secrets.token_urlsafe(32)
    digest = hashlib.sha256(state.encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.oauth_state_minutes)
    with get_connection() as conn:
        conn.execute("DELETE FROM oauth_states WHERE expires_at <= NOW()")
        conn.execute(
            "INSERT INTO oauth_states(provider,state_hash,expires_at) VALUES(%s,%s,%s)",
            (provider, digest, expires),
        )
        conn.commit()
    return state


def _consume_state(provider: str, state: str) -> bool:
    digest = hashlib.sha256(state.encode()).hexdigest()
    with get_connection() as conn:
        row = conn.execute(
            """DELETE FROM oauth_states
               WHERE provider=%s AND state_hash=%s AND expires_at>NOW()
               RETURNING id""",
            (provider, digest),
        ).fetchone()
        conn.commit()
    return bool(row)


def _issue_login(user_id, provider: str, provider_subject: str, provider_email: str | None, full_name: str):
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM auth_identities WHERE provider=%s AND provider_subject=%s",
            (provider, provider_subject),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE auth_identities SET provider_email=%s,last_login_at=NOW() WHERE id=%s",
                (provider_email, existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO auth_identities(user_id,provider,provider_subject,provider_email)
                   VALUES(%s,%s,%s,%s)""",
                (user_id, provider, provider_subject, provider_email),
            )
        conn.commit()
    with get_connection() as conn:
        approval = conn.execute("SELECT approval_status FROM users WHERE id=%s", (user_id,)).fetchone()
    if not approval or approval["approval_status"] != "approved":
        raise HTTPException(403, "RSS AI Project Manager account is awaiting administrator approval")
    token, expires = create_session(str(user_id))
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires,
        "provider": provider,
        "user": {"id": str(user_id), "email": provider_email, "full_name": full_name},
        "workspaces": user_workspaces({"id": user_id}),
    }


def _find_or_create_social_user(provider: str, subject: str, email: str | None, name: str):
    with get_connection() as conn:
        identity = conn.execute(
            """SELECT u.id,u.email,u.full_name
               FROM auth_identities i JOIN users u ON u.id=i.user_id
               WHERE i.provider=%s AND i.provider_subject=%s""",
            (provider, subject),
        ).fetchone()
        if identity:
            return identity["id"], identity["email"], identity["full_name"]

        if email:
            user = conn.execute(
                "SELECT id,email,full_name,approval_status FROM users WHERE lower(email)=lower(%s)",
                (email,),
            ).fetchone()
            if user:
                # A social provider may only attach to an existing account when
                # the provider has supplied a verified/authoritative email.
                conn.execute(
                    "UPDATE users SET email_verified=TRUE,updated_at=NOW() WHERE id=%s",
                    (user["id"],),
                )
                conn.commit()
                return user["id"], user["email"], user["full_name"]

        user = conn.execute(
            """INSERT INTO users(email,full_name,password_hash,email_verified,approval_status)
               VALUES(%s,%s,NULL,TRUE,'pending')
               RETURNING id,email,full_name""",
            (email or f"{provider}_{subject}@oauth.invalid", name.strip() or "Customer"),
        ).fetchone()
        ws = conn.execute(
            "INSERT INTO workspaces(name,owner_user_id) VALUES(%s,%s) RETURNING id,name",
            (f"{user['full_name']}'s Workspace", user["id"]),
        ).fetchone()
        conn.execute(
            "INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')",
            (ws["id"], user["id"]),
        )
        conn.execute(
            "INSERT INTO service_entitlements(workspace_id,service_key,enabled) VALUES(%s,'project_manager',FALSE)",
            (ws["id"],),
        )
        for service in ("rss_core", "rss_kit", "ray"):
            conn.execute(
                "INSERT INTO service_entitlements(workspace_id,service_key,enabled) VALUES(%s,%s,FALSE)",
                (ws["id"], service),
            )
        conn.commit()
        return user["id"], user["email"], user["full_name"]


@router.post("/register", status_code=202)
async def register(item: RegisterRequest):
    try:
        pw = hash_password(item.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    request_id = str(uuid4())
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email)=lower(%s)", (item.email,)).fetchone():
            raise HTTPException(409, "Account already exists")
        user = conn.execute(
            """INSERT INTO users(email,full_name,password_hash,approval_status,approval_request_id)
               VALUES(lower(%s),%s,%s,'pending',%s)
               RETURNING id,email,full_name,email_verified,approval_status,approval_request_id""",
            (item.email, item.full_name.strip(), pw, request_id),
        ).fetchone()
        ws = conn.execute(
            "INSERT INTO workspaces(name,owner_user_id) VALUES(%s,%s) RETURNING id,name",
            (item.workspace_name.strip(), user["id"]),
        ).fetchone()
        conn.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')", (ws["id"], user["id"]))
        conn.execute("INSERT INTO service_entitlements(workspace_id,service_key,enabled) VALUES(%s,'project_manager',FALSE)", (ws["id"],))
        for service in ("rss_core", "rss_kit", "ray"):
            conn.execute("INSERT INTO service_entitlements(workspace_id,service_key,enabled) VALUES(%s,%s,FALSE)", (ws["id"], service))
        verification_token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO email_verifications(user_id,token_hash,expires_at) VALUES(%s,%s,%s)",
            (user["id"], hashlib.sha256(verification_token.encode()).hexdigest(), datetime.now(timezone.utc) + timedelta(hours=24)),
        )
        conn.commit()
    verify_url = _app_url("/auth/verify-email?token=" + quote(verification_token))
    try:
        await _send_template(item.email, settings.resend_verify_template_id, {"USER_NAME": item.full_name.strip(), "VERIFY_URL": verify_url})
    except Exception as exc:
        with get_connection() as conn:
            conn.execute("DELETE FROM users WHERE id=%s", (user["id"],))
            conn.commit()
        raise HTTPException(503, "Verification email could not be sent. Please try again.") from exc
    return {
        "status": "email_verification_required",
        "message": "Account created. Check your email and verify it. After verification, RSS Core will receive the approval request.",
        "user": {"id": str(user["id"]), "email": user["email"], "full_name": user["full_name"]},
    }

@router.get("/verify-email")
async def verify_email(token: str):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with get_connection() as conn:
        row = conn.execute(
            """SELECT u.id,u.email,u.full_name,u.approval_status,u.approval_request_id
               FROM email_verifications ev JOIN users u ON u.id=ev.user_id
               WHERE ev.token_hash=%s AND ev.expires_at>NOW() AND ev.verified_at IS NULL""",
            (token_hash,),
        ).fetchone()
        if not row:
            raise HTTPException(400, "Verification link is invalid or expired")
        conn.execute("UPDATE email_verifications SET verified_at=NOW() WHERE token_hash=%s", (token_hash,))
        conn.execute("UPDATE users SET email_verified=TRUE,email_verified_at=NOW(),updated_at=NOW() WHERE id=%s", (row["id"],))
        conn.commit()
    try:
        await _submit_to_rss_core(str(row["id"]), str(row["approval_request_id"]), row["email"], row["full_name"])
    except Exception as exc:
        raise HTTPException(502, "Email verified, but the RSS Core approval request could not be submitted. Please retry verification later.") from exc
    return {"verified": True, "status": "pending_approval", "message": "Email verified. Your approval request has been sent to RSS Core."}


@router.post("/login")
def login(item: LoginRequest):
    with get_connection() as conn:
        user = conn.execute(
            """SELECT id,email,full_name,email_verified,password_hash,approval_status
               FROM users WHERE lower(email)=lower(%s)""",
            (item.email,),
        ).fetchone()
    if not user or not verify_password(item.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    if user["approval_status"] == "pending":
        raise HTTPException(403, "Account is awaiting RSS AI Project Manager administrator approval")
    if user["approval_status"] == "rejected":
        raise HTTPException(403, "This RSS AI Project Manager account was rejected")
    if user["approval_status"] == "suspended":
        raise HTTPException(403, "This RSS AI Project Manager account is suspended")
    token, expires = create_session(str(user["id"]))
    data = dict(user)
    data.pop("password_hash", None)
    workspaces = user_workspaces({"id": user["id"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires,
        "user": data,
        "workspaces": workspaces,
        "workspace": workspaces[0] if workspaces else None,
    }


@router.post("/logout")
def logout(user: dict = Depends(require_auth), authorization: str | None = Header(default=None)):
    # Bearer token is read explicitly so only the current session is revoked.
    if not authorization:
        raise HTTPException(401, "Authentication required")
    revoke_session(authorization[7:].strip() if authorization.startswith("Bearer ") else authorization)
    return {"status": "logged_out"}


@router.get("/{provider}/start")
def oauth_start(provider: str):
    client_id, client_secret, authorize_url = _oauth_config(provider)
    if not client_id or not client_secret:
        raise HTTPException(503, f"{provider.title()} OAuth is not configured")
    state = _new_state(provider)
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(provider),
        "response_type": "code",
        "state": state,
    }
    if provider == "google":
        params.update({"scope": "openid email profile", "access_type": "online", "prompt": "select_account"})
    else:
        params["scope"] = "read:user user:email"
    return RedirectResponse(authorize_url + "?" + urlencode(params), status_code=302)


@router.get("/{provider}/callback")
async def oauth_callback(provider: str, code: str, state: str):
    client_id, client_secret, _ = _oauth_config(provider)
    if not client_id or not client_secret or not _consume_state(provider, state):
        raise HTTPException(400, "Invalid or expired OAuth state")
    redirect_uri = _redirect_uri(provider)

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        if provider == "google":
            token_response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )
            if token_response.status_code != 200:
                raise HTTPException(401, "Google authorization failed")
            access_token = token_response.json().get("access_token")
            profile_response = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if profile_response.status_code != 200:
                raise HTTPException(401, "Google profile lookup failed")
            profile = profile_response.json()
            subject = profile.get("sub")
            email = profile.get("email") if profile.get("email_verified") else None
            name = profile.get("name") or profile.get("email") or "Customer"
        else:
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            if token_response.status_code != 200:
                raise HTTPException(401, "GitHub authorization failed")
            access_token = token_response.json().get("access_token")
            profile_response = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            if profile_response.status_code != 200:
                raise HTTPException(401, "GitHub profile lookup failed")
            profile = profile_response.json()
            subject = str(profile.get("id"))
            email = profile.get("email")
            if not email:
                emails_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
                )
                if emails_response.status_code == 200:
                    verified = [e for e in emails_response.json() if e.get("verified")]
                    primary = next((e for e in verified if e.get("primary")), None)
                    email = (primary or (verified[0] if verified else {})).get("email")
            name = profile.get("name") or profile.get("login") or "Customer"

    if not subject:
        raise HTTPException(401, "OAuth provider did not return a stable account identifier")
    user_id, user_email, user_name = _find_or_create_social_user(provider, subject, email, name)
    return _issue_login(user_id, provider, subject, user_email, user_name)
