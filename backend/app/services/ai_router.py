from dataclasses import dataclass
import os

import urllib.error
import urllib.request
import json


@dataclass(frozen=True)
class AIResponse:
    provider: str
    model: str
    content: str


class AIProviderRouter:
    """Provider-independent router with Ollama-first local execution and hosted fallbacks."""

    def __init__(self) -> None:
        self.ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def generate(self, prompt: str) -> AIResponse:
        errors: list[str] = []
        try:
            return self._ollama(prompt)
        except Exception as exc:
            errors.append(f"ollama: {exc}")

        if self.gemini_api_key:
            try:
                return self._gemini(prompt)
            except Exception as exc:
                errors.append(f"gemini: {exc}")

        raise RuntimeError("No AI provider available; " + "; ".join(errors))

    def _ollama(self, prompt: str) -> AIResponse:
        payload = json.dumps({"model": self.ollama_model, "prompt": prompt, "stream": False}).encode()
        request = urllib.request.Request(
            f"{self.ollama_url.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode())
        return AIResponse("ollama", self.ollama_model, data["response"])

    def _gemini(self, prompt: str) -> AIResponse:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.gemini_model}:generateContent?key={self.gemini_api_key}"
        )
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode())
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return AIResponse("gemini", self.gemini_model, text)
