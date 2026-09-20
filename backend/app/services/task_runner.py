from datetime import datetime, timezone
import json
import os
import urllib.request

from ..db import get_connection
from .autopilot import Autopilot
from .ray_client import RayClient, RayUnavailable
from ..core.config import settings


class TaskRunner:
    """Execute central AI tasks with persistent RSS project and GitHub context."""

    def __init__(self, autopilot: Autopilot | None = None) -> None:
        self.autopilot = autopilot or Autopilot()
        self.github_token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        self.ray = RayClient()

    def run_next(self) -> dict:
        with get_connection() as conn:
            task = conn.execute(
                "SELECT id,project_id,conversation_id,workspace_id,title,status,operation,arguments,command,context "
                "FROM tasks WHERE status='pending' ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1"
            ).fetchone()
            if task is None:
                return {"status": "idle"}
            entitlement = conn.execute(
                "SELECT enabled FROM service_entitlements WHERE workspace_id=%s AND service_key='project_manager'",
                (task["workspace_id"],),
            ).fetchone()
            if not entitlement or not entitlement["enabled"]:
                conn.execute("UPDATE tasks SET status='blocked',updated_at=NOW() WHERE id=%s AND workspace_id=%s", (task["id"],task["workspace_id"]))
                conn.commit()
                return {"status":"blocked","task_id":task["id"],"error":"Project Manager service is disabled for this workspace"}
            conn.execute("UPDATE tasks SET status='running',started_at=COALESCE(started_at,NOW()),updated_at=NOW() WHERE id=%s AND workspace_id=%s AND status='pending'", (task["id"],task["workspace_id"]))
            conn.commit()

        try:
            context = self._load_context(task["workspace_id"],task["project_id"],task["conversation_id"])
            if task["context"]:
                context = f"{context}\nTASK_CONTEXT:\n{task['context']}"
            command=task["command"]
            if isinstance(command,str):
                try: command=json.loads(command)
                except json.JSONDecodeError: command=None
            try:
                ray_env_enabled=os.getenv("RSS_RAY_EXECUTE_TASKS","").lower() in {"1","true","yes"}
                if not settings.ray_execute_tasks or not ray_env_enabled:
                    raise RayUnavailable("RAY execution is disabled until explicitly enabled")
                result=self.ray.execute(str(task["id"]),self._project_repository(task["workspace_id"],task["project_id"]),task["title"],context,command)
                if result["status"]=="completed":
                    self._finish(task["id"],task["workspace_id"],task["project_id"],"completed",result.get("output",""),"ray",{"ray_task_id":result["ray_task_id"],"operation":task["operation"],"arguments":task["arguments"] or {}})
                    return {"status":"completed","task_id":task["id"],"provider":"ray","output":result.get("output",""),"ray_task_id":result["ray_task_id"]}
                raise RuntimeError(result.get("error","RAY task failed"))
            except RayUnavailable:
                result=self.autopilot.execute(task["title"],context)
                self._finish(task["id"],task["workspace_id"],task["project_id"],"completed",result.output,result.provider)
                return {"status":"completed","task_id":task["id"],"provider":result.provider,"model":result.model,"output":result.output,"execution_path":"internal-autopilot-fallback"}
        except Exception as exc:
            self._finish(task["id"],task["workspace_id"],task["project_id"],"failed",str(exc))
            return {"status":"failed","task_id":task["id"],"error":str(exc)}

    def _load_context(self,workspace_id: str,project_id: str|None,conversation_id: int|None) -> str:
        with get_connection() as conn:
            parts=[]; repository=None
            if project_id:
                project=conn.execute("SELECT id,name,repository,enabled,priority FROM projects WHERE id=%s AND workspace_id=%s",(project_id,workspace_id)).fetchone()
                if project:
                    repository=project["repository"]
                    parts.append(f"PROJECT: {project['name']}\nPROJECT_ID: {project['id']}\nREPOSITORY: {repository}\nENABLED: {project['enabled']}\nPRIORITY: {project['priority']}")
                memories=conn.execute("SELECT memory_type,memory_key,content FROM project_memory WHERE project_id=%s AND workspace_id=%s ORDER BY updated_at DESC LIMIT 30",(project_id,workspace_id)).fetchall()
                parts.extend(f"MEMORY {r['memory_type']}/{r['memory_key']}: {r['content']}" for r in memories)
            if repository:
                gh=self._github_context(repository)
                if gh: parts.append(gh)
            if conversation_id:
                messages=conn.execute("SELECT m.role,m.content FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE c.id=%s AND c.workspace_id=%s ORDER BY m.created_at DESC,m.id DESC LIMIT 20",(conversation_id,workspace_id)).fetchall()
                parts.extend(f"{r['role'].upper()}: {r['content']}" for r in reversed(messages))
            return "\n".join(parts)

    def _project_repository(self,workspace_id: str,project_id: str|None) -> str:
        if not project_id: return "RSS-AI-Project-Manager"
        with get_connection() as conn:
            row=conn.execute("SELECT repository FROM projects WHERE id=%s AND workspace_id=%s",(project_id,workspace_id)).fetchone()
        return (row["repository"] if row and row["repository"] else "RSS-AI-Project-Manager").split("/")[-1]

    def _github_context(self,repository: str) -> str:
        allowed={item.strip().lower() for item in settings.github_allowed_repositories.split(",") if item.strip()}
        if repository.lower() not in allowed: return "GITHUB_CONTEXT_BLOCKED: repository is not on the server-side allowlist"
        headers={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2026-03-10","User-Agent":"RSS-AI-Project-Manager"}
        if self.github_token: headers["Authorization"]=f"Bearer {self.github_token}"
        try:
            repo=self._github_get(f"https://api.github.com/repos/{repository}",headers)
            commits=self._github_get(f"https://api.github.com/repos/{repository}/commits?per_page=5",headers)
            issues=self._github_get(f"https://api.github.com/repos/{repository}/issues?state=open&per_page=10",headers)
            readme=self._github_get(f"https://api.github.com/repos/{repository}/readme",headers)
            lines=["LIVE GITHUB CONTEXT:",f"default_branch={repo.get('default_branch')}",f"language={repo.get('language')}",f"open_issues={repo.get('open_issues_count')}",f"archived={repo.get('archived')}","RECENT_COMMITS:"]
            for commit in commits if isinstance(commits,list) else []:
                lines.append(f"- {commit.get('sha','')[:8]} {commit.get('commit',{}).get('message','').splitlines()[0]}")
            lines.append("OPEN_ISSUES:")
            for issue in issues if isinstance(issues,list) else []: lines.append(f"- #{issue.get('number')} {issue.get('title','')}")
            if isinstance(readme,dict) and readme.get("content"):
                import base64
                lines.extend(["README_EXCERPT:",base64.b64decode(readme["content"]).decode("utf-8",errors="replace")[:6000]])
            return "\n".join(lines)
        except Exception as exc:
            return f"GITHUB_CONTEXT_ERROR: {type(exc).__name__}"

    @staticmethod
    def _github_get(url: str,headers: dict) -> dict|list:
        request=urllib.request.Request(url,headers=headers)
        with urllib.request.urlopen(request,timeout=20) as response: return json.loads(response.read().decode("utf-8"))

    def _finish(self,task_id: int,workspace_id: str,project_id: str|None,status: str,summary: str,provider: str|None=None,metadata: dict|None=None) -> None:
        with get_connection() as conn:
            conn.execute("UPDATE tasks SET status=%s,provider=%s,completed_at=CASE WHEN %s='completed' THEN NOW() ELSE completed_at END,updated_at=%s WHERE id=%s AND workspace_id=%s",(status,provider,status,datetime.now(timezone.utc),task_id,workspace_id))
            conn.execute("INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata) VALUES(%s,%s,%s,%s,%s::jsonb)",(project_id,workspace_id,"task."+status,summary[:1000],json.dumps({"provider":provider,**(metadata or {})})))
            conn.commit()
