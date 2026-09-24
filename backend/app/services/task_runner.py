import json
import os
import urllib.request
from ..core.config import settings
from ..db import get_connection
from .ray_client import RayClient, RayUnavailable

class TaskRunner:
    """Claim PM tasks and delegate execution exclusively to RSS Core/RAY."""
    def __init__(self) -> None:
        self.github_token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        self.ray = RayClient()

    def run_next(self) -> dict:
        with get_connection() as conn:
            task = conn.execute("SELECT id,project_id,conversation_id,workspace_id,title,status,operation,arguments,command,context FROM tasks WHERE status='pending' AND (next_retry_at IS NULL OR next_retry_at<=NOW()) ORDER BY priority NULLS LAST,created_at,id LIMIT 1 FOR UPDATE SKIP LOCKED").fetchone()
            if task is None: return {"status":"idle"}
            entitlement = conn.execute("SELECT enabled FROM service_entitlements WHERE workspace_id=%s AND service_key='project_manager'",(task["workspace_id"],)).fetchone()
            if not entitlement or not entitlement["enabled"]:
                self._set_state(conn,task,"blocked","Project Manager service is disabled for this workspace","control-plane"); conn.commit(); return {"status":"blocked","task_id":task["id"]}
            conn.execute("UPDATE tasks SET status='dispatched',started_at=COALESCE(started_at,NOW()),attempts=COALESCE(attempts,0)+1,updated_at=NOW() WHERE id=%s AND workspace_id=%s AND status='pending'",(task["id"],task["workspace_id"])); conn.commit()
        try:
            context=self._load_context(task["workspace_id"],task["project_id"],task["conversation_id"])
            if task["context"]: context=f"{context}\\nTASK_CONTEXT:\\n{task['context']}"
            command=task["command"]
            if isinstance(command,str):
                try: command=json.loads(command)
                except json.JSONDecodeError: command=None
            enabled=os.getenv("RSS_RAY_EXECUTE_TASKS","true").lower() in {"1","true","yes"}
            if not settings.ray_execute_tasks or not enabled: return self._block(task,"RAY execution is not enabled for this deployment")
            repository = self._project_repository(task["workspace_id"],task["project_id"])
            if not command:
                command = self._default_execution_command(
                    repository,
                    str(task["title"] or ""),
                    context,
                )
                if not command:
                    return self._block(task,"RAY execution command is not configured")
            self._state(task,"running","Task accepted for RSS Core/RAY execution")
            result=self.ray.execute(str(task["id"]),repository,task["title"],context,command)
            if result["status"]=="completed":
                self._finish(task,"completed",result.get("output",""),"ray",{"ray_task_id":result["ray_task_id"]}); return {"status":"completed","task_id":task["id"],"provider":"ray","ray_task_id":result["ray_task_id"]}
            return self._fail_or_retry(task,result.get("error","RAY task failed"),result.get("ray_task_id"))
        except RayUnavailable as exc: return self._block(task,str(exc))
        except Exception as exc: return self._fail_or_retry(task,str(exc),None)

    def _default_execution_command(self, repository: str, title: str, context: str) -> list[str] | None:
        if not repository or "/" not in repository or not title:
            return None
        # RSS Core/RAY is the sole execution path. The RAY worker exposes a
        # dedicated non-shell executable for the PM engine; no shell syntax or
        # credentials are sent in the task payload.
        return [
            "rss-project-manager-executor",
            repository,
            title,
            context,
        ]

    def _set_state(self,conn,task,status,summary,provider):
        conn.execute("UPDATE tasks SET status=%s,provider=%s,updated_at=NOW() WHERE id=%s AND workspace_id=%s",(status,provider,task["id"],task["workspace_id"]))
        conn.execute("INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata) VALUES(%s,%s,%s,%s,%s::jsonb)",(task["project_id"],task["workspace_id"],"task."+status,summary[:1000],json.dumps({"provider":provider,"execution_path":"rss-core-cloudflare-ray"})))
    def _state(self,task,status,summary):
        with get_connection() as conn: self._set_state(conn,task,status,summary,"ray"); conn.commit()
    def _block(self,task,reason):
        with get_connection() as conn:
            conn.execute("UPDATE tasks SET status='blocked',provider='ray',blocked=true,last_error=%s,updated_at=NOW() WHERE id=%s AND workspace_id=%s",(reason[:2000],task["id"],task["workspace_id"]))
            conn.execute("INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata) VALUES(%s,%s,'task.blocked',%s,%s::jsonb)",(task["project_id"],task["workspace_id"],reason[:1000],json.dumps({"execution_path":"rss-core-cloudflare-ray"}))); conn.commit()
        return {"status":"blocked","task_id":task["id"],"provider":"ray","error":reason,"execution_path":"rss-core-cloudflare-ray"}
    def _fail_or_retry(self,task,reason,ray_task_id):
        with get_connection() as conn:
            row=conn.execute("SELECT attempts FROM tasks WHERE id=%s AND workspace_id=%s",(task["id"],task["workspace_id"])).fetchone(); attempts=int(row["attempts"] or 0) if row else 1
            status="retry_queued" if attempts<3 else "failed"
            if attempts<3: conn.execute("UPDATE tasks SET status='pending',provider='ray',last_error=%s,next_retry_at=NOW()+(INTERVAL '60 seconds'),updated_at=NOW() WHERE id=%s AND workspace_id=%s",(reason[:2000],task["id"],task["workspace_id"]))
            else: conn.execute("UPDATE tasks SET status='failed',provider='ray',last_error=%s,updated_at=NOW() WHERE id=%s AND workspace_id=%s",(reason[:2000],task["id"],task["workspace_id"]))
            conn.execute("INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata) VALUES(%s,%s,%s,%s,%s::jsonb)",(task["project_id"],task["workspace_id"],"task."+status,reason[:1000],json.dumps({"provider":"ray","ray_task_id":ray_task_id,"attempts":attempts}))); conn.commit()
        return {"status":status,"task_id":task["id"],"provider":"ray","error":reason}
    def _finish(self,task,status,summary,provider,metadata):
        with get_connection() as conn:
            conn.execute("UPDATE tasks SET status=%s,provider=%s,last_error=NULL,blocked=false,completed_at=NOW(),updated_at=NOW() WHERE id=%s AND workspace_id=%s",(status,provider,task["id"],task["workspace_id"]))
            conn.execute("INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata) VALUES(%s,%s,%s,%s,%s::jsonb)",(task["project_id"],task["workspace_id"],"task."+status,summary[:1000],json.dumps({"provider":provider,**metadata}))); conn.commit()
    def _load_context(self,workspace_id,project_id,conversation_id):
        with get_connection() as conn:
            parts=[]; repository=None
            if project_id:
                project=conn.execute("SELECT id,name,repository,enabled,priority FROM projects WHERE id=%s AND workspace_id=%s",(project_id,workspace_id)).fetchone()
                if project: repository=project["repository"]; parts.append(f"PROJECT: {project['name']}\\nPROJECT_ID: {project['id']}\\nREPOSITORY: {repository}\\nENABLED: {project['enabled']}\\nPRIORITY: {project['priority']}")
                memories=conn.execute("SELECT memory_type,memory_key,content FROM project_memory WHERE project_id=%s AND workspace_id=%s ORDER BY updated_at DESC LIMIT 30",(project_id,workspace_id)).fetchall(); parts.extend(f"MEMORY {r['memory_type']}/{r['memory_key']}: {r['content']}" for r in memories)
            if repository:
                gh=self._github_context(repository)
                if gh: parts.append(gh)
            if conversation_id:
                messages=conn.execute("SELECT m.role,m.content FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.id=%s AND c.workspace_id=%s ORDER BY m.created_at DESC,m.id DESC LIMIT 20",(conversation_id,workspace_id)).fetchall(); parts.extend(f"{r['role'].upper()}: {r['content']}" for r in reversed(messages))
            return "\\n".join(parts)
    def _project_repository(self,workspace_id,project_id):
        if not project_id: return "RSS-AI-Project-Manager"
        with get_connection() as conn: row=conn.execute("SELECT repository FROM projects WHERE id=%s AND workspace_id=%s",(project_id,workspace_id)).fetchone()
        repository = row["repository"] if row and row["repository"] else "riyazamra1/RSS-AI-Project-Manager"
        if "/" not in repository:
            repository = "riyazamra1/" + repository
        return repository
    def _github_context(self,repository):
        allowed={item.strip().lower() for item in settings.github_allowed_repositories.split(",") if item.strip()}
        if repository.lower() not in allowed: return "GITHUB_CONTEXT_BLOCKED: repository is not on the server-side allowlist"
        headers={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2026-03-10","User-Agent":"RSS-AI-Project-Manager"};
        if self.github_token: headers["Authorization"]=f"Bearer {self.github_token}"
        try:
            repo=self._github_get(f"https://api.github.com/repos/{repository}",headers); commits=self._github_get(f"https://api.github.com/repos/{repository}/commits?per_page=5",headers); issues=self._github_get(f"https://api.github.com/repos/{repository}/issues?state=open&per_page=10",headers); readme=self._github_get(f"https://api.github.com/repos/{repository}/readme",headers)
            lines=["LIVE GITHUB CONTEXT:",f"default_branch={repo.get('default_branch')}",f"language={repo.get('language')}",f"open_issues={repo.get('open_issues_count')}",f"archived={repo.get('archived')}","RECENT_COMMITS:"]; lines.extend(f"- {c.get('sha','')[:8]} {c.get('commit',{}).get('message','').splitlines()[0]}" for c in commits if isinstance(commits,list)); lines.append("OPEN_ISSUES:"); lines.extend(f"- #{i.get('number')} {i.get('title','')}" for i in issues if isinstance(issues,list))
            if isinstance(readme,dict) and readme.get("content"):
                import base64; lines.extend(["README_EXCERPT:",base64.b64decode(readme["content"]).decode("utf-8",errors="replace")[:6000]])
            return "\\n".join(lines)
        except Exception as exc: return f"GITHUB_CONTEXT_ERROR: {type(exc).__name__}"
    @staticmethod
    def _github_get(url,headers):
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20) as response: return json.loads(response.read().decode("utf-8"))
