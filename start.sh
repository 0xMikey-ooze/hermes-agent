#!/bin/bash
set -e

# Hermes + Swarm AGI startup script
# Validates dependencies, then launches Hermes in gateway mode

echo "Checking dependencies..."

# Check AGI server
if [ -z "$AGI_SERVER_URL" ]; then
  echo "ERROR: AGI_SERVER_URL not set. Start the AGI server first:"
  echo "   node /path/to/swarm/src/mcp/agi-server-http.js"
  exit 1
fi

echo -n "  AGI server at $AGI_SERVER_URL... "
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$AGI_SERVER_URL/health" 2>/dev/null || echo "000")
if [ "$HTTP_STATUS" != "200" ]; then
  echo "FAILED (HTTP $HTTP_STATUS)"
  exit 1
fi
echo "OK"

# Check git
echo -n "  git... "
git --version > /dev/null 2>&1 && echo "OK" || { echo "FAILED: git not found"; exit 1; }

# Check node (for AGI server)
echo -n "  node... "
node --version > /dev/null 2>&1 && echo "OK" || { echo "FAILED: node not found"; exit 1; }

echo ""
echo "Starting Hermes..."
python cli.py --gateway --no-tui "$@"
