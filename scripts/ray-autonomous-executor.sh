#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${1:?repository required}"
TASK="${2:?task required}"
CONTEXT="${3:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="$ROOT/config/projects.json"
CONTRACT="$ROOT/GEMINI.md"
ROUTER="$ROOT/scripts/agent-router.sh"
WORKDIR="${RUNNER_TEMP:-/tmp}/rss-ray-pm-${RAY_TASK_ID:-manual}-$(date +%s)"
mkdir -p "$WORKDIR"
trap 'rm -rf "$WORKDIR"' EXIT

if [[ -z "${RSS_RAY_GITHUB_TOKEN:-}" && -z "${GH_TOKEN:-}" ]]; then
  echo "FAIL: RSS_RAY_GITHUB_TOKEN/GH_TOKEN is required on the RAY worker" >&2
  exit 20
fi

export GH_TOKEN="${GH_TOKEN:-$RSS_RAY_GITHUB_TOKEN}"

python3 - "$PROJECTS" "$REPOSITORY" <<'PY'
import json,sys
data=json.load(open(sys.argv[1],encoding='utf-8'))
allowed={p['repository'] for p in data['projects'] if p.get('enabled')}
if sys.argv[2] not in allowed:
    raise SystemExit(f"Repository is not enabled: {sys.argv[2]}")
PY

if ! command -v git >/dev/null 2>&1 || ! command -v bash >/dev/null 2>&1; then
  echo "FAIL: RAY worker is missing git or bash" >&2
  exit 25
fi

mkdir -p "$WORKDIR/agent"
git clone --depth=1 "https://github.com/$REPOSITORY.git" "$WORKDIR/repo"
cd "$WORKDIR/repo"

cat > "$WORKDIR/task.txt" <<EOF
RSS AI PROJECT MANAGER RAY TASK
Repository: $REPOSITORY
Task: $TASK

Authoritative worker contract:
$(cat "$CONTRACT")

Additional task context:
$CONTEXT

Execution rules:
- RAY is the execution engine; do not use or invoke any Autopilot engine.
- Do not commit, push, merge, or create a pull request from the AI worker.
- Preserve useful existing changes and run relevant checks.
EOF

if command -v openhands >/dev/null 2>&1; then
  OPENHANDS_SUPPRESS_BANNER=1 openhands --headless --json --override-with-envs --exit-without-confirmation -t "$(cat "$WORKDIR/task.txt")" | tee "$WORKDIR/agent/openhands.jsonl"
elif [[ "${RSS_OPENHANDS_DOCKER_ENABLED:-false}" == "true" ]] && command -v docker >/dev/null 2>&1; then
  IMAGE="${RSS_OPENHANDS_DOCKER_IMAGE:-docker.openhands.dev/openhands/openhands:1.8}"
  docker run --rm --pull=missing \
    -e LLM_API_KEY -e LLM_MODEL -e LLM_BASE_URL \
    -e GEMINI_API_KEY -e GEMINI_MODEL \
    -v "$PWD:/workspace" -w /workspace \
    "$IMAGE" openhands --headless --json --override-with-envs --exit-without-confirmation -t "$(cat "$WORKDIR/task.txt")" | tee "$WORKDIR/agent/openhands.jsonl"
elif command -v gemini >/dev/null 2>&1 || command -v codex >/dev/null 2>&1; then
  bash "$ROUTER" "$WORKDIR/task.txt" "$WORKDIR/agent"
else
  echo "FAIL: no RAY AI execution route available" >&2
  exit 26
fi

if [[ -x ./gradlew ]]; then
  ./gradlew assembleDebug --stacktrace
elif [[ -f package.json ]]; then
  npm test --if-present
  npm run build --if-present
elif [[ -f Makefile ]]; then
  make
else
  echo "No supported build system detected."
  exit 2
fi

if git status --porcelain | grep -E '(^|/)(\.env|.*\.jks|.*\.keystore|.*\.p12|.*\.pem)$' >/dev/null; then
  echo "BLOCKED: credential/signing file detected"
  exit 30
fi

echo "RSS_PM_RAY_EXECUTION_OK"
