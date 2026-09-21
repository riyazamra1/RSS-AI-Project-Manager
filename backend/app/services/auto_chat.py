from datetime import datetime, timezone
from ..db import get_connection
from .ai_router import AIProviderRouter

class AutomaticProjectChat:
    def run_due(self, limit: int = 10) -> dict:
        processed = []
        for _ in range(limit):
            with get_connection() as conn:
                row = conn.execute("""SELECT s.id,s.workspace_id,s.project_id,s.interval_minutes,p.name,p.description,p.status
                    FROM project_chat_schedules s JOIN projects p ON p.id=s.project_id AND p.workspace_id=s.workspace_id
                    WHERE s.enabled=true AND s.next_run_at IS NOT NULL AND s.next_run_at<=NOW()
                    ORDER BY s.next_run_at,s.id LIMIT 1 FOR UPDATE SKIP LOCKED""").fetchone()
                if row is None: break
                conn.execute("UPDATE project_chat_schedules SET next_run_at=NOW() + (interval_minutes || ' minutes')::interval, last_run_at=NOW(), updated_at=NOW() WHERE id=%s",(row["id"],))
                conn.commit()
            try:
                prompt = (f"You are automatically checking project '{row['name']}'. Provide a concise project check-in: current state, recent risks/blockers, what should happen next, and any user decision needed. Do not claim work was completed unless recorded in project data.\nProject status: {row['status']}\nDescription: {row['description'] or ''}")
                result = AIProviderRouter().generate(prompt)
                with get_connection() as conn:
                    conv = conn.execute("INSERT INTO conversations(project_id,workspace_id,title) VALUES(%s,%s,%s) RETURNING id",(row["project_id"],row["workspace_id"],f"Automatic project check-in — {row['name']}")).fetchone()
                    conn.execute("INSERT INTO messages(conversation_id,role,content,provider,model) VALUES(%s,'assistant',%s,%s,%s)",(conv["id"],result.content,result.provider,result.model))
                    conn.execute("INSERT INTO activity_log(project_id,workspace_id,event_type,summary,metadata) VALUES(%s,%s,'project.auto_chat',%s,%s::jsonb)",(row["project_id"],row["workspace_id"],"Automatic project check-in generated",f'{{"provider":"{result.provider}","interval_minutes":{row["interval_minutes"]}}}'))
                    conn.commit()
                processed.append({"project_id":row["project_id"],"conversation_id":conv["id"],"provider":result.provider,"status":"completed"})
            except Exception as exc:
                processed.append({"project_id":row["project_id"],"status":"failed","error":type(exc).__name__})
        return {"processed":len(processed),"items":processed,"checked_at":datetime.now(timezone.utc).isoformat()}
