from dataclasses import dataclass
from datetime import datetime, timezone

from .ai_router import AIProviderRouter


@dataclass(frozen=True)
class AutopilotResult:
    status: str
    provider: str
    model: str
    output: str
    completed_at: str


class Autopilot:
    """Small deterministic execution layer for project-management AI tasks."""

    def __init__(self, router: AIProviderRouter | None = None) -> None:
        self.router = router or AIProviderRouter()

    def execute(self, task: str, context: str = "") -> AutopilotResult:
        prompt = (
            "You are the RSS AI Project Manager execution agent.\n"
            "Analyze the task, use the supplied context, and return a concise actionable result.\n\n"
            f"TASK:\n{task}\n\nCONTEXT:\n{context}"
        )
        result = self.router.generate(prompt)
        return AutopilotResult(
            status="completed",
            provider=result.provider,
            model=result.model,
            output=result.content,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
