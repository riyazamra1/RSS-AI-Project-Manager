"""GitHub repository discovery for the RSS project registry.

The service deliberately has no fixed project-count limit. Curated project metadata
wins over generated defaults, while newly discovered repositories are added as
managed projects. Repositories can be excluded explicitly in config/projects.json.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "projects.json"


def _load_registry() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _github_repositories(owner: str) -> list[dict]:
    token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "RSS-AI-Project-Manager"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(f"https://api.github.com/users/{owner}/repos?per_page=100&type=all", headers=headers)
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _matches(name: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        if re.match(regex, name, flags=re.IGNORECASE):
            return True
    return False


def discover_projects() -> dict:
    registry = _load_registry()
    discovery = registry.get("discovery", {})
    if not discovery.get("enabled", False):
        return {"discovered": 0, "added": 0, "projects": registry.get("projects", [])}

    owner = discovery["owner"]
    excludes = {name.lower() for name in discovery.get("exclude_repositories", [])}
    patterns = discovery.get("include_patterns", [])
    existing = {item["repository"].lower(): item for item in registry.get("projects", [])}
    next_priority = max((int(item.get("priority", 0)) for item in existing.values()), default=0) + 1
    added = 0

    for repo in _github_repositories(owner):
        name = repo.get("name", "")
        if not name or name.lower() in excludes or not _matches(name, patterns):
            continue
        full_name = repo.get("full_name", f"{owner}/{name}")
        if full_name.lower() in existing:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        category = "system" if any(token in name.lower() for token in ("autopilot", "devops")) else "product"
        if "game" in name.lower() or name.lower() in {"rss-omi-kings", "rss-flux-runner"}:
            category = "game"
        existing[full_name.lower()] = {
            "id": slug,
            "name": name.replace("_", " ").upper(),
            "repository": full_name,
            "enabled": True,
            "priority": next_priority,
            "category": category,
            "discovered": True,
        }
        next_priority += 1
        added += 1

    projects = sorted(existing.values(), key=lambda item: (int(item.get("priority", 999999)), item["id"]))
    return {"discovered": len(projects), "added": added, "projects": projects}
