#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8000}"

echo "Killing any process on port $PORT..."
PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
  kill -9 "$PID" 2>/dev/null || true
  echo "Killed PID $PID on port $PORT"
else
  echo "No process found on port $PORT"
fi
