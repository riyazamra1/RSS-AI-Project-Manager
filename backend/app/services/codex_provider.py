from dataclasses import dataclass
import json
import os
import urllib.request


@dataclass(frozen=True)
class CodexResponse:
    provider: str
    model: str
    content: str


class CodexProvider:
    """OpenAI Responses API adapter for Codex-style coding/reasoning workloads."""

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model = os.getenv("CODEX_MODEL", "gpt-5.6-luna")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str) -> CodexResponse:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        payload = json.dumps({
            "model": self.model,
            "input": prompt,
        }).encode()
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/responses",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode())
        text = data.get("output_text")
        if not text:
            parts = []
            for item in data.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        parts.append(content.get("text", ""))
            text = "\n".join(parts).strip()
        if not text:
            raise RuntimeError("OpenAI response contained no text output")
        return CodexResponse("codex", self.model, text)
