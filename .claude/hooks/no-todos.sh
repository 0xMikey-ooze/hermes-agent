#!/usr/bin/env bash
# PostToolUse hook: warns when incomplete code markers are found after a file write.
# Advisory only — always exits 0.
# Reads JSON from stdin (Claude hook protocol): {tool_input: {file_path, path, ...}}

set -o pipefail

# Read stdin JSON
INPUT=$(cat)

# Extract file path
FILE=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null)

# If jq not available or file empty, skip silently
if [ -z "$FILE" ] || [ "$FILE" = "null" ]; then
  exit 0
fi

# Only act on files that exist
if [ ! -f "$FILE" ]; then
  exit 0
fi

# Grep for incomplete code markers (case-insensitive)
MATCHES=$(grep -n -i \
  -e 'TODO' \
  -e 'FIXME' \
  -e 'HACK' \
  -e 'XXX' \
  -e 'PLACEHOLDER' \
  -e 'implement later' \
  -e 'stub' \
  "$FILE" 2>/dev/null || true)

if [ -n "$MATCHES" ]; then
  echo ""
  echo "⚠️  WARNING: Found incomplete code markers in $FILE:"
  echo "$MATCHES"
  echo ""
  echo "  → Document blockers in output/blockers.md instead of leaving TODOs."
  echo "  → Write real code or skip the feature. Do not commit stubs."
  echo ""
fi

# Always exit 0 — advisory only, never blocks the write
exit 0
