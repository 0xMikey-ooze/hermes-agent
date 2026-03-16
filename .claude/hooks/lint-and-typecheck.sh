#!/usr/bin/env bash
# PostToolUse hook: runs tsc + eslint after every file write.
# Advisory only — always exits 0 so the write is never blocked.
# Reads JSON from stdin (Claude hook protocol): {tool_input: {file_path, path, ...}}

set -o pipefail

# Read stdin JSON — Claude passes tool_input as JSON on stdin
INPUT=$(cat)

# Extract file path from JSON — try file_path first, then path
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null)

# If jq not available or file empty, skip silently
if [ -z "$FILE" ] || [ "$FILE" = "null" ]; then
  exit 0
fi

# Only act on files that actually exist on disk
if [ ! -f "$FILE" ]; then
  exit 0
fi

# ── TypeScript typecheck (for .ts / .tsx files) ──────────────────────────────
case "$FILE" in
  *.ts|*.tsx)
    echo "🔍 [typecheck] Checking $FILE..."
    if [ -f "tsconfig.json" ]; then
      npx tsc --noEmit 2>&1 | head -30 || true
    else
      echo "  [typecheck] No tsconfig.json found — skipping tsc"
    fi
    ;;
esac

# ── ESLint (for .ts / .tsx / .js / .jsx files) ───────────────────────────────
case "$FILE" in
  *.ts|*.tsx|*.js|*.jsx)
    echo "🔍 [eslint] Linting $FILE..."
    if npx eslint --version >/dev/null 2>&1; then
      npx eslint --fix "$FILE" 2>&1 | head -20 || true
    else
      echo "  [eslint] eslint not available — skipping"
    fi
    ;;
esac

# Always exit 0 — advisory hook, never blocks the write
exit 0
