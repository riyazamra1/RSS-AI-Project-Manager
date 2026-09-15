#!/usr/bin/env bash
set -euo pipefail
REPOSITORY="${1:?repository required}"
TASK="${2:?task required}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROJECTS="$ROOT/config/projects.json"
CONTRACT="$ROOT/GEMINI.md"
ROUTER="$ROOT/scripts/agent-router.sh"
python3 - "$PROJECTS" "$REPOSITORY" <<'PY'
import json,sys
data=json.load(open(sys.argv[1],encoding='utf-8'))
allowed={p['repository'] for p in data['projects'] if p.get('enabled')}
if sys.argv[2] not in allowed: raise SystemExit(f'Repository is not enabled: {sys.argv[2]}')
PY
export GH_TOKEN="${RSS_AUTOPILOT_GITHUB_TOKEN:?Set RSS_AUTOPILOT_GITHUB_TOKEN}"
WORKDIR="${RUNNER_TEMP:-/tmp}/rss-autopilot-${GITHUB_RUN_ID:-manual}"
mkdir -p "$WORKDIR"
trap 'rm -rf "$WORKDIR"' EXIT
gh repo clone "$REPOSITORY" "$WORKDIR/repo" -- --depth=1
cd "$WORKDIR/repo"
BRANCH="autopilot/${GITHUB_RUN_ID:-manual}-$(date +%Y%m%d%H%M%S)"
git checkout -b "$BRANCH"
cat > "$WORKDIR/task.txt" <<EOF
RSS AI PROJECT MANAGER AUTOPILOT TASK
Repository: $REPOSITORY
Task: $TASK

Authoritative worker contract:
$(cat "$CONTRACT")

Do not commit or push from the worker. Preserve useful existing changes and run relevant checks.
EOF
mkdir -p "$WORKDIR/agent"
bash "$ROUTER" "$WORKDIR/task.txt" "$WORKDIR/agent"
if [[ -x ./gradlew ]]; then ./gradlew assembleDebug --stacktrace; elif [[ -f package.json ]]; then npm test --if-present; npm run build --if-present; elif [[ -f Makefile ]]; then make; else echo 'No supported build system detected.'; exit 2; fi
if git status --porcelain | grep -E '(^|/)(\.env|.*\.jks|.*\.keystore|.*\.p12|.*\.pem)$' >/dev/null; then echo 'BLOCKED: credential/signing file detected'; exit 30; fi
git add -A
git config user.name "RSS AI Project Manager"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "autopilot: ${TASK:0:72}"
gh auth setup-git
git push --set-upstream origin "$BRANCH"
gh pr create --repo "$REPOSITORY" --head "$BRANCH" --base main --title "RSS Autopilot: ${TASK:0:70}" --body "Automated by the internal RSS Autopilot engine. Build/check passed. Merge remains manual."
