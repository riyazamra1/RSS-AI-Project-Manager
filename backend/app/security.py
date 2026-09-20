import hashlib, hmac, json, secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, Header, HTTPException
from .db import get_connection
from .core.config import settings

def hash_password(password: str) -> str:
    if len(password) < 12: raise ValueError("Password must be at least 12 characters")
    salt=secrets.token_bytes(16); rounds=310000
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,rounds)
    return "pbkdf2_sha256$"+str(rounds)+"$"+salt.hex()+"$"+digest.hex()

def verify_password(password: str, encoded: str|None) -> bool:
    if not encoded: return False
    try:
        algo, rounds, salt, digest=encoded.split("$",3)
        candidate=hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),int(rounds))
        return algo=="pbkdf2_sha256" and hmac.compare_digest(candidate.hex(),digest)
    except (ValueError,TypeError): return False

def token_hash(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()

def create_session(user_id: str):
    token=secrets.token_urlsafe(48)
    expires=datetime.now(timezone.utc)+timedelta(days=settings.session_days)
    with get_connection() as conn:
        conn.execute("INSERT INTO sessions(user_id,token_hash,expires_at) VALUES(%s,%s,%s)",(user_id,token_hash(token),expires)); conn.commit()
    return token,expires

def require_auth(authorization: str|None=Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "): raise HTTPException(401,"Authentication required")
    token=authorization[7:].strip()
    with get_connection() as conn:
        row=conn.execute("""SELECT u.id,u.email,u.full_name,u.email_verified,s.id session_id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.revoked_at IS NULL AND s.expires_at>NOW()""",(token_hash(token),)).fetchone()
    if not row: raise HTTPException(401,"Invalid or expired session")
    return dict(row)

def workspace_access(user:dict,workspace_id:str,minimum_role="viewer"):
    levels={"viewer":1,"member":2,"developer":3,"manager":4,"admin":5,"owner":6}
    with get_connection() as conn:
        row=conn.execute("""SELECT wm.workspace_id,wm.user_id,wm.role,w.name FROM workspace_members wm JOIN workspaces w ON w.id=wm.workspace_id WHERE wm.workspace_id=%s AND wm.user_id=%s AND w.status='active'""",(workspace_id,user["id"])).fetchone()
    if not row or levels.get(row["role"],0)<levels[minimum_role]: raise HTTPException(403,"Workspace access denied")
    return dict(row)

def service_access(user:dict,workspace_id:str,service_key:str):
    workspace_access(user,workspace_id)
    with get_connection() as conn: row=conn.execute("SELECT enabled FROM service_entitlements WHERE workspace_id=%s AND service_key=%s",(workspace_id,service_key)).fetchone()
    if not row or not row["enabled"]: raise HTTPException(403,"Service is not enabled for this workspace")
    return row

def audit(user,workspace_id,action,resource_type=None,resource_id=None,metadata=None):
    with get_connection() as conn:
        conn.execute("INSERT INTO audit_log(workspace_id,user_id,action,resource_type,resource_id,metadata) VALUES(%s,%s,%s,%s,%s,%s::jsonb)",(workspace_id,user["id"],action,resource_type,resource_id,json.dumps(metadata or {}))); conn.commit()
