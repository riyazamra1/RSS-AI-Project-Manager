#!/usr/bin/env bash
set -euo pipefail
PROMPT_FILE="${1:?prompt file required}"
LOG_DIR="${2:?log directory required}"
mkdir -p "$LOG_DIR"
AGENT_STATE_FILE="$LOG_DIR/agent-state.txt"
GEMINI_PRIMARY_MODEL="${GEMINI_MODEL:-}"
GEMINI_FALLBACK_MODEL="${GEMINI_FALLBACK_MODEL:-gemini-3.1-flash-lite}"
AGENT="${RSS_AUTOPILOT_AGENT:-auto}"
[[ "$AGENT" == auto ]] && AGENT=codex
is_quota_error(){ grep -Eiq '429|quota|rate.?limit|exhausted.*daily|RESOURCE_EXHAUSTED' "$1"; }
run_gemini_model(){ local model="$1" output="$2"; if [[ -n "$model" ]]; then gemini --model "$model" --approval-mode=yolo --skip-trust --output-format=json -p "$(cat "$PROMPT_FILE")" > "$output" 2>&1; else gemini --approval-mode=yolo --skip-trust --output-format=json -p "$(cat "$PROMPT_FILE")" > "$output" 2>&1; fi; }
run_gemini(){ local output="$1"; local primary="${output%.json}.primary.json"; local fallback="${output%.json}.fallback.json"; set +e; run_gemini_model "$GEMINI_PRIMARY_MODEL" "$primary"; local status=$?; set -e; if [[ $status -eq 0 ]]; then cp "$primary" "$output"; return 0; fi; if ! is_quota_error "$primary"; then cp "$primary" "$output"; return "$status"; fi; set +e; run_gemini_model "$GEMINI_FALLBACK_MODEL" "$fallback"; local fallback_status=$?; set -e; cat "$primary" "$fallback" > "$output"; [[ $fallback_status -eq 0 ]] && printf '%s\n' gemini-fallback > "$AGENT_STATE_FILE"; return "$fallback_status"; }
if [[ "$AGENT" == codex && -n "${CODEX_API_KEY:-}" ]]; then set +e; codex exec --sandbox workspace-write --ephemeral --json -o "$LOG_DIR/codex.jsonl" < "$PROMPT_FILE"; status=$?; set -e; if [[ $status -eq 0 ]]; then printf '%s\n' codex > "$AGENT_STATE_FILE"; exit 0; fi; fi
printf '%s\n' gemini > "$AGENT_STATE_FILE"
run_gemini "$LOG_DIR/gemini.json"
