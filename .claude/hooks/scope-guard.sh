#!/usr/bin/env bash
# PreToolUse hook: enforces file ownership boundaries between teams.
# Blocks writes outside a team's allowed paths (exits 1 = deny).
# Reads JSON from stdin (Claude hook protocol): {tool_input: {file_path, path, ...}}

set -o pipefail

# Read stdin JSON
INPUT=$(cat)

# Extract file path
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null)

# If jq not available or file empty, allow (can't enforce without path)
if [ -z "$FILE" ] || [ "$FILE" = "null" ]; then
  exit 0
fi

# Read current team identity (written by swarm.js teamScript before claude runs)
TEAM_FILE="/tmp/swarm-local-20260315-232322-26058/team-1/.swarm/current-team.txt"
if [ ! -f "$TEAM_FILE" ]; then
  # No team file — can't enforce scope, allow
  exit 0
fi

TEAM=$(cat "$TEAM_FILE" 2>/dev/null | tr -d '[:space:]')

# ── Normalize file path (strip leading ./ for consistent matching) ────────────
NORM_FILE="${FILE#./}"

# ── Files ALL teams can always write ─────────────────────────────────────────
# .swarm/, output/, PLAN.md, any .md file, any config file at repo root
case "$NORM_FILE" in
  .swarm/*|output/*|tasks/*|PLAN.md|*.md|*.json|*.yaml|*.yml|*.toml|*.env.example)
    exit 0
    ;;
esac

# ── Path traversal guard ──────────────────────────────────────────────────────
# Reject paths with .. to prevent bypassing scope via relative traversal
if echo "$NORM_FILE" | grep -q '\.\.'; then
  echo "⚠️  SCOPE GUARD: Rejected path traversal attempt: $FILE"
  exit 1
fi

# ── Team-specific allowed paths ──────────────────────────────────────────────
check_backend() {
  case "$NORM_FILE" in
    src/api/*|src/middleware/*|src/models/*|\
    prisma/*|lib/*|utils/*|db/*|server/*|\
    routes/*|controllers/*|services/*|\
    src/lib/*|src/utils/*|src/server/*|\
    src/routes/*|src/controllers/*|src/services/*|\
    src/db/*)
      exit 0
      ;;
  esac
}

check_frontend() {
  case "$NORM_FILE" in
    src/components/*|src/pages/*|src/app/*|\
    src/hooks/*|src/styles/*|src/ui/*|\
    public/*|styles/*|components/*|pages/*|app/*|\
    src/context/*|src/store/*)
      exit 0
      ;;
  esac
}

check_qa() {
  case "$NORM_FILE" in
    tests/*|__tests__/*|spec/*|\
    cypress/*|playwright/*|e2e/*|\
    *.test.ts|*.test.tsx|*.test.js|*.spec.ts|*.spec.tsx|*.spec.js)
      exit 0
      ;;
  esac
  # QA can read anywhere (only write-blocked here, but we check tool type)
  # For reads, exit 0. For writes outside qa paths: fall through to deny.
}

case "$TEAM" in
  backend)
    check_backend
    ;;
  frontend)
    check_frontend
    ;;
  qa)
    check_qa
    ;;
  *)
    # Unknown team — allow (fail open to avoid blocking unknown teams)
    exit 0
    ;;
esac

# ── Denied — file is outside this team's scope ───────────────────────────────
echo ""
echo "⚠️  SCOPE GUARD: File '$FILE' is outside your team scope (team: $TEAM)."
echo ""
echo "   Document needed changes in /tmp/swarm-local-20260315-232322-26058/team-1/.swarm/cross-team-requests.md:"
echo "   - File: $FILE"
echo "   - What change is needed and why"
echo "   - Which team owns this file"
echo ""
exit 1
