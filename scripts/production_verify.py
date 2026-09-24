#!/usr/bin/env python3
"""Non-destructive production verification for RSS Core -> RAY.

Required:
  RSS_CORE_URL
  RSS_CORE_API_TOKEN

Optional:
  RAY_POLL_SECONDS (default 5)
  RAY_TIMEOUT_SECONDS (default 120)
  RAY_WORKER_URL (when supplied, its /health endpoint is checked)
  RAY_WORKER_TOKEN (optional Bearer token for worker health)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def request(url: str, token: str | None = None, method: str = "GET", payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Accept": "application/json", "User-Agent": "RSS-AI-Project-Manager-production-verify"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read(1024 * 1024)
        return json.loads(raw.decode("utf-8")) if raw else {}


def main() -> int:
    base = os.environ.get("RSS_CORE_URL", "").rstrip("/")
    token = os.environ.get("RSS_CORE_API_TOKEN", "")
    if not base or not token:
        print("FAIL: RSS_CORE_URL and RSS_CORE_API_TOKEN are required", file=sys.stderr)
        return 2
    if base.startswith("http://"):
        print("FAIL: RSS_CORE_URL must use HTTPS", file=sys.stderr)
        return 2

    try:
        health = request(base + "/health")
        print("RSS Core health:", json.dumps(health, separators=(",", ":")))
    except Exception as exc:
        print("FAIL: RSS Core /health:", type(exc).__name__, file=sys.stderr)
        return 1

    worker_url = os.environ.get("RAY_WORKER_URL", "").rstrip("/")
    if worker_url:
        worker_token = os.environ.get("RAY_WORKER_TOKEN", "")
        try:
            worker_health = request(worker_url + "/health", worker_token or None)
            print("RAY worker health:", json.dumps(worker_health, separators=(",", ":")))
        except Exception as exc:
            print("FAIL: RAY worker /health:", type(exc).__name__, file=sys.stderr)
            return 1

    task_id = "rss-production-verify-" + str(int(time.time()))
    payload = {
        "id": task_id,
        "project": "RSS-AI-Project-Manager",
        "task": "Production connectivity smoke test",
        "context": "Non-destructive production verification. Return the exact marker only.",
        "command": ["printf", "RSS_RAY_PRODUCTION_OK"],
        "priority": "normal",
    }

    try:
        result = request(base + "/api/v1/ray/tasks", token, "POST", payload)
    except urllib.error.HTTPError as exc:
        print(f"FAIL: RAY task submission HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:
        print("FAIL: RAY task submission:", type(exc).__name__, file=sys.stderr)
        return 1

    if not result.get("queued"):
        try:
            result = request(base + "/api/v1/ray/dispatch", token, "POST", payload)
        except Exception as exc:
            print("FAIL: RAY direct dispatch:", type(exc).__name__, file=sys.stderr)
            return 1

    ray_id = str(result.get("task", {}).get("id", ""))
    if not ray_id:
        print("FAIL: RSS Core did not return an accepted RAY task id", file=sys.stderr)
        return 1

    print("RAY accepted task:", ray_id)
    deadline = time.monotonic() + int(os.environ.get("RAY_TIMEOUT_SECONDS", "120"))
    interval = max(1, int(os.environ.get("RAY_POLL_SECONDS", "5")))
    while time.monotonic() < deadline:
        try:
            status = request(base + "/api/v1/ray/tasks/" + ray_id, token)
        except Exception as exc:
            print("FAIL: RAY status polling:", type(exc).__name__, file=sys.stderr)
            return 1
        state = status.get("status")
        print("RAY status:", state)
        if state == "completed":
            output = str(status.get("stdout", "")).strip()
            if output != "RSS_RAY_PRODUCTION_OK":
                print("FAIL: unexpected RAY output", file=sys.stderr)
                return 1
            print("PASS: RSS Core -> RAY authenticated production round-trip")
            return 0
        if state == "failed":
            print("FAIL: RAY task failed", file=sys.stderr)
            return 1
        time.sleep(interval)

    print("FAIL: RAY task polling timeout", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
