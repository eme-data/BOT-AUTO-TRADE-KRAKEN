#!/usr/bin/env bash
# Setup script for Kraken Trading Bot
set -euo pipefail

echo "=== Kraken Trading Bot Setup ==="

# 1. Copy env file
if [ ! -f .env ]; then
    cp .env.example .env
    echo "[OK] Created .env from .env.example"
    echo "     -> Edit .env with DB/Redis/Dashboard passwords"
else
    echo "[SKIP] .env already exists"
fi

# 2. Setup nginx config (HTTP-only by default)
if [ ! -f nginx/nginx-active.conf ]; then
    cp nginx/nginx-init.conf nginx/nginx-active.conf
    echo "[OK] Created nginx HTTP config (run scripts/init-ssl.sh for HTTPS)"
fi

# 3. Create Python virtual environment
if [ ! -d venv ]; then
    python3 -m venv venv
    echo "[OK] Created virtual environment"
fi

source venv/bin/activate 2>/dev/null || source venv/Scripts/activate 2>/dev/null

# 4. Install dependencies
pip install --upgrade pip
pip install -r requirements/dev.txt
echo "[OK] Installed Python dependencies"

# 5. Frontend
if command -v npm &>/dev/null; then
    cd dashboard/frontend
    npm install
    cd ../..
    echo "[OK] Installed frontend dependencies"
else
    echo "[SKIP] npm not found – frontend not installed"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Quick start:"
echo "  1. Edit .env (DB/Redis passwords only)"
echo "  2. docker compose up -d                 # start all services"
echo "  3. Open http://localhost → configure Kraken API from the dashboard"
echo ""
echo "For HTTPS:"
echo "  1. Set DOMAIN and CERT_EMAIL in .env"
echo "  2. bash scripts/init-ssl.sh"
echo ""
echo "For local development:"
echo "  docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build"
