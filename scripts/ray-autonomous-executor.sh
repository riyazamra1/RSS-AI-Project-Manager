#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${1:?repository required}"
TASK="${2:?task required}"
CONTEXT="${3:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="${RUNNER_TEMP:-/tmp}/rss-ray-pm-${RAY_TASK_ID:-manual}-$(date +%s)"
mkdir -p "$WORKDIR"
trap 'rm -rf "$WORKDIR"' EXIT

if [[ -z "${RSS_AUTOPILOT_GITHUB_TOKEN:-}" && -z "${GH_TOKEN:-}" ]]; then
  echo "FAIL: RSS_AUTOPILOT_GITHUB_TOKEN/GH_TOKEN is required on the RAY worker" >&2
  exit 20
fi

export GH_TOKEN="${GH_TOKEN:-$RSS_AUTOPILOT_GITHUB_TOKEN}"

# The existing internal autopilot engine owns checkout, AI work, build/test,
# credential protection, commit, push and PR creation. RAY only supplies the
# task and worker secrets; credentials never travel in the task payload.
bash "$ROOT/scripts/autopilot.sh" "$REPOSITORY" "$TASK" "$CONTEXT"

echo "RSS_PM_AUTONOMOUS_EXECUTION_OK"
