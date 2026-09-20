from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from ..db import get_connection
from ..security import hash_password, verify_password, create_session

router=APIRouter(prefix="/auth",tags=["auth"])

class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str=Field(min_length=2,max_length=200)
    password: str=Field(min_length=12,max_length=200)
    workspace_name: str=Field(min_length=2,max_length=200)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str=Field(min_length=1,max_length=200)

@router.post("/register",status_code=201)
def register(item:RegisterRequest):
    try: pw=hash_password(item.password)
    except ValueError as exc: raise HTTPException(422,str(exc))
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE lower(email)=lower(%s)",(item.email,)).fetchone(): raise HTTPException(409,"Account already exists")
        user=conn.execute("INSERT INTO users(email,full_name,password_hash) VALUES(lower(%s),%s,%s) RETURNING id,email,full_name,email_verified",(item.email,item.full_name.strip(),pw)).fetchone()
        ws=conn.execute("INSERT INTO workspaces(name,owner_user_id) VALUES(%s,%s) RETURNING id,name",(item.workspace_name.strip(),user["id"])).fetchone()
        conn.execute("INSERT INTO workspace_members(workspace_id,user_id,role) VALUES(%s,%s,'owner')",(ws["id"],user["id"]))
        conn.execute("INSERT INTO service_entitlements(workspace_id,service_key,enabled) VALUES(%s,'project_manager',TRUE)",(ws["id"],))
        for service in ("rss_core","rss_kit","ray"): conn.execute("INSERT INTO service_entitlements(workspace_id,service_key,enabled) VALUES(%s,%s,FALSE)",(ws["id"],service))
        conn.commit()
    token,expires=create_session(str(user["id"]))
    return {"access_token":token,"token_type":"bearer","expires_at":expires,"user":dict(user),"workspace":dict(ws)}

@router.post("/login")
def login(item:LoginRequest):
    with get_connection() as conn: user=conn.execute("SELECT id,email,full_name,email_verified,password_hash FROM users WHERE lower(email)=lower(%s)",(item.email,)).fetchone()
    if not user or not verify_password(item.password,user["password_hash"]): raise HTTPException(401,"Invalid email or password")
    token,expires=create_session(str(user["id"]))
    data=dict(user); data.pop("password_hash",None)
    return {"access_token":token,"token_type":"bearer","expires_at":expires,"user":data}

@router.post("/logout")
def logout():
    return {"status":"client token revocation endpoint requires authenticated route wiring"}
