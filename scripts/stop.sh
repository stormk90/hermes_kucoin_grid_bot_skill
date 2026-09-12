#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Deteniendo servicios de Hermes Grid Bot y Dashboard..."

if [ -f "data/grid_bot.pid" ]; then
    kill "$(cat data/grid_bot.pid)" 2>/dev/null || true
    rm -f data/grid_bot.pid
fi

if [ -f "data/erp_web.pid" ]; then
    kill "$(cat data/erp_web.pid)" 2>/dev/null || true
    rm -f data/erp_web.pid
fi

pkill -f "core/grid_bot.py" 2>/dev/null || true
pkill -f "erp_dashboard/app.py" 2>/dev/null || true

echo "✅ Todos los servicios han sido detenidos de forma segura."
