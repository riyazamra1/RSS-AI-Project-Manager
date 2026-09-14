#!/usr/bin/env python3
"""Synchronize the RSS project registry from GitHub and build a dynamic queue.

GitHub is the repository inventory source of truth. config/projects.json remains
policy/configuration: discovery patterns and explicit exclusions are preserved.
"""

from __future__ import annotations

import fnmatch
import json
import os
import pathlib
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "config" / "projects.json"
GENERATED = ROOT / "config" / "generated-tasks.json"
STATE = ROOT / "config" / "scheduler-state.json"
OWNER = "riyazamra1"


def github_get(url: str, token: str) -> object:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def repo_matches(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)


def project_id(name: str) -> str:
    value = name.lower().replace("_", "-")
    value = "-".join(part for part in value.split("-") if part)
    return value


def display_name(name: str) -> str:
    if name == "RSS-Flux-Runner":
        return "FLUX RUNNER"
    return name.replace("_", " ").replace("-", " ").upper()


def category(name: str) -> str:
    lower = name.lower()
    if "website" in lower:
        return "website"
    if any(x in lower for x in ("game", "puzzle", "flux-runner", "omi-kings", "liquid-flow")):
        return "game"
    if any(x in lower for x in ("core", "server", "deploy")):
        return "infrastructure"
    return "product"


def main() -> None:
    token = os.getenv("RSS_AUTOPILOT_GITHUB_TOKEN") or os.getenv("RSS_GITHUB_TOKEN") or ""
    with PROJECTS.open(encoding="utf-8") as f:
        config = json.load(f)

    discovery = config.setdefault("discovery", {})
    patterns = discovery.get("include_patterns", [])
    excludes = set(discovery.get("exclude_repositories", []))
    # Keep the actual current website repo name supported as well as the legacy spelling.
    if "Razeen-Secure-Solution-Website" not in patterns:
        patterns.append("Razeen-Secure-Solution-Website")
    excludes.update({"RSS-AI-Project-Manager", "RSS-Autopilot", "RSS-Project-Autopilot", "RSS_Invoice_and_Estimate"})

    repositories: list[dict] = []
    page = 1
    while True:
        batch = github_get(f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated", token)
        if not batch:
            break
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    existing = {p.get("repository"): p for p in config.get("projects", [])}
    discovered: list[dict] = []
    for repo in repositories:
        name = repo.get("name", "")
        if not name or repo.get("fork"):
            continue
        if name in excludes or not repo_matches(name, patterns):
            continue
        full = repo.get("full_name") or f"{OWNER}/{name}"
        old = existing.get(full, {})
        discovered.append({
            "id": old.get("id") or project_id(name),
            "name": old.get("name") or display_name(name),
            "repository": full,
            "enabled": old.get("enabled", True),
            "priority": old.get("priority", 1000),
            "category": old.get("category") or category(name),
            "discovered": True,
            "default_branch": repo.get("default_branch", "main"),
            "archived": bool(repo.get("archived")),
        })

    discovered.sort(key=lambda p: (not p["enabled"], p["priority"], p["repository"].lower()))
    config["version"] = max(int(config.get("version", 1)), 5)
    config["discovery"]["last_sync"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    config["discovery"]["github_repository_count"] = len(repositories)
    config["discovery"]["active_project_count"] = sum(1 for p in discovered if p["enabled"] and not p["archived"])
    config["projects"] = discovered

    PROJECTS.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    state = {"cursor": 0}
    if STATE.exists():
        try:
            state.update(json.loads(STATE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    state["project_count"] = len(discovered)
    state["active_project_count"] = sum(1 for p in discovered if p["enabled"] and not p["archived"])
    state["repositories_seen"] = len(repositories)
    STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    print(f"GitHub repositories seen: {len(repositories)}")
    print(f"Active discovered RSS projects: {state['active_project_count']}")


if __name__ == "__main__":
    main()
