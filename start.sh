#!/usr/bin/env bash
set -e

# ─────────────────────────────────────────────────────────
#  Kopiiki — One-click start script
#  Starts both the Flask backend and Vite frontend.
# ─────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[kopiiki]${NC} $1"; }
ok()    { echo -e "${GREEN}[  ✓  ]${NC} $1"; }
fail()  { echo -e "${RED}[  ✗  ]${NC} $1"; exit 1; }

# ── Step 1: Check prerequisites ──────────────────────────

info "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 || fail "Python 3 is required but not installed."
ok "Python 3 found: $(python3 --version 2>&1)"

command -v node >/dev/null 2>&1 || fail "Node.js is required but not installed."
ok "Node.js found: $(node --version)"

command -v npm >/dev/null 2>&1 || fail "npm is required but not installed."
ok "npm found: $(npm --version)"

# ── Step 2: Setup backend ────────────────────────────────

info "Setting up backend..."

if [ ! -d "$BACKEND_DIR/venv" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$BACKEND_DIR/venv"
fi

source "$BACKEND_DIR/venv/bin/activate"

info "Installing Python dependencies..."
pip install -q -r "$BACKEND_DIR/requirements.txt"

# Check if Playwright browsers are installed
if ! python3 -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(); b.close(); p.stop()" 2>/dev/null; then
    info "Installing Playwright Chromium browser..."
    playwright install chromium
fi

ok "Backend ready"

# ── Step 3: Setup frontend ───────────────────────────────

info "Setting up frontend..."

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    info "Installing Node.js dependencies..."
    cd "$FRONTEND_DIR" && npm install
fi

ok "Frontend ready"

# ── Step 4: Start services ───────────────────────────────

info "Starting services..."

# Kill any existing processes on our ports
lsof -ti :5002 | xargs kill -9 2>/dev/null || true
lsof -ti :5176 | xargs kill -9 2>/dev/null || true

# Start backend in background
cd "$BACKEND_DIR"
source venv/bin/activate
nohup python3 app.py > "$ROOT_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
ok "Backend started (PID: $BACKEND_PID, port 5002)"

# Cleanup function
cleanup() {
    info "Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start frontend in foreground (so user sees output and can Ctrl+C)
cd "$FRONTEND_DIR"

echo ""
echo -e "${BOLD}────────────────────────────────────────────${NC}"
echo -e "${BOLD}  🔮 Kopiiki is starting up!${NC}"
echo -e "${BOLD}────────────────────────────────────────────${NC}"
echo ""
echo -e "  Frontend:  ${CYAN}http://localhost:5176${NC}"
echo -e "  Backend:   ${CYAN}http://localhost:5002${NC}"
echo -e "  Logs:      ${CYAN}$ROOT_DIR/backend.log${NC}"
echo ""
echo -e "  Press ${BOLD}Ctrl+C${NC} to stop all services."
echo ""

npm run dev -- --port 5176
