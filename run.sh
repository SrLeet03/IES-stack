#!/bin/bash
# Start both backend (FastAPI) and frontend (Next.js) for development.
# Usage: ./run.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Load nvm if available
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"
nvm use 22 2>/dev/null || true

echo "=== Starting IES RDE Filing Tool ==="

# Activate Python venv
source "$PROJECT_DIR/venv/bin/activate"

# Start backend
echo "[Backend] Starting FastAPI on :8000..."
cd "$PROJECT_DIR"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Start frontend
echo "[Frontend] Starting Next.js on :3000..."
cd "$PROJECT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
