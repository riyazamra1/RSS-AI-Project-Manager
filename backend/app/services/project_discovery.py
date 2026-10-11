"""GitHub repository discovery and PostgreSQL project synchronization."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from app.db import get_connection

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "projects.json"


def _load_registry() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _github_repositories(owner: str) -> list[dict]:
    token = os.getenv("RSS_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "RSS-AI-Project-Manager",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    repos: list[dict] = []
    page = 1
    while True:
        if token:
            url = f"https://api.github.com/user/repos?per_page=100&page={page}&affiliation=owner,collaborator,organization_member&sort=full_name"
        else:
            # Public repository discovery also works without a GitHub token.
            url = f"https://api.github.com/users/{owner}/repos?per_page=100&page={page}&type=owner&sort=full_name"
        req = Request(url, headers=headers)
        with urlopen(req, timeout=20) as response:
            batch = json.loads(response.read().decode("utf-8"))
        if not isinstance(batch, list):
            raise RuntimeError(f"GitHub repository API returned unexpected response: {batch}")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return [repo for repo in repos if repo.get("owner", {}).get("login", "").lower() == owner.lower()]


def _matches(name: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
        if re.match(regex, name, flags=re.IGNORECASE):
            return True
    return False


def _sync_projects(projects: list[dict]) -> int:
    """Persist every discovered RSS repository into each active workspace."""
    synced = 0
    with get_connection() as conn:
        workspaces = conn.execute("SELECT id FROM workspaces WHERE status='active' ORDER BY created_at").fetchall()
        for workspace in workspaces:
            workspace_id = str(workspace["id"])
            suffix = workspace_id.replace("-", "")[:10]
            for project in projects:
                canonical_id = str(project["id"])
                project_id = f"{canonical_id[:105]}-{suffix}"
                conn.execute(
                    """INSERT INTO projects
                        (id,name,repository,enabled,priority,workspace_id,description)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (id) DO UPDATE SET
                        name=EXCLUDED.name, repository=EXCLUDED.repository,
                        enabled=EXCLUDED.enabled, priority=EXCLUDED.priority,
                        description=COALESCE(EXCLUDED.description,projects.description),
                        updated_at=NOW()
                    WHERE projects.workspace_id=EXCLUDED.workspace_id""",
                    (project_id, project["name"], project.get("repository"),
                     project.get("enabled", True), int(project.get("priority", 999999)),
                     workspace_id, project.get("description")),
                )
                synced += 1
        conn.commit()
    return synced

def discover_projects() -> dict:
    registry = _load_registry()
    discovery = registry.get("discovery", {})

    if not discovery.get("enabled", False):
        projects = registry.get("projects", [])
        _sync_projects(projects)
        return {"discovered": len(projects), "added": 0, "projects": projects}

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
        category = "system"
        if "game" in name.lower() or name.lower() in {"rss-omi-kings", "rss-flux-runner"}:
            category = "game"
        elif not any(token in name.lower() for token in ("autopilot", "devops")):
            category = "product"

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
    synced = _sync_projects(projects)
    return {"discovered": len(projects), "added": added, "synced": synced, "projects": projects}
