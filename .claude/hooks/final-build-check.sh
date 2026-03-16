#!/usr/bin/env bash
# Stop hook: runs the project build after Claude finishes a session.
# Reports pass/fail but does NOT block (exits 0 always).
# Reads JSON from stdin (Claude hook protocol): Stop event has no tool_input.

set -o pipefail

# Consume stdin (Stop hook still passes JSON context)
INPUT=$(cat)

# ── Determine build command ───────────────────────────────────────────────────
# Check for bun first (faster), then npm, then plain tsc
if [ -f "package.json" ]; then
  if command -v bun >/dev/null 2>&1 && grep -q '"build"' package.json 2>/dev/null; then
    BUILD_CMD="bun run build"
  elif grep -q '"build"' package.json 2>/dev/null; then
    BUILD_CMD="npm run build"
  elif grep -q '"typecheck"' package.json 2>/dev/null; then
    BUILD_CMD="npm run typecheck"
  else
    # No build script — try tsc directly
    BUILD_CMD="npx tsc --noEmit"
  fi
elif [ -f "tsconfig.json" ]; then
  BUILD_CMD="npx tsc --noEmit"
else
  echo "ℹ️  [build-check] No package.json or tsconfig.json found — skipping build check"
  exit 0
fi

# ── Run the build ─────────────────────────────────────────────────────────────
echo ""
echo "🔨 [build-check] Running: $BUILD_CMD"
echo "────────────────────────────────────────"

BUILD_OUTPUT=$(eval "$BUILD_CMD" 2>&1)
BUILD_EXIT=$?

echo "$BUILD_OUTPUT" | tail -30

echo "────────────────────────────────────────"
if [ $BUILD_EXIT -ne 0 ]; then
  echo "❌ BUILD FAILED — fix errors before committing."
  echo "   Run: $BUILD_CMD"
else
  echo "✅ Build passed."
fi
echo ""

# Always exit 0 — advisory hook, never blocks Stop
exit 0
