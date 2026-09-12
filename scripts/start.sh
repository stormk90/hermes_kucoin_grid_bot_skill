#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f ".env" ]; then
    echo "❌ Archivo .env no encontrado. Ejecuta primero ./scripts/install.sh"
    exit 1
fi

echo "🚀 Iniciando Hermes Grid Bot y Panel ERP Web..."

# Activar entorno virtual
source venv/bin/activate

# Iniciar Grid Bot en segundo plano
nohup python3 core/grid_bot.py > data/grid_bot.log 2>&1 &
BOT_PID=$!
echo "✅ Grid Bot iniciado (PID: $BOT_PID) -> data/grid_bot.log"

# Iniciar Dashboard ERP Web
nohup python3 erp_dashboard/app.py > data/erp_web.log 2>&1 &
ERP_PID=$!
echo "✅ Dashboard ERP iniciado (PID: $ERP_PID) -> http://localhost:5000"

echo "$BOT_PID" > data/grid_bot.pid
echo "$ERP_PID" > data/erp_web.pid

echo "==================================================="
echo "🎯 Bot y Dashboard en ejecución."
echo "🌐 Abre tu navegador en: http://localhost:5000"
echo "Para detener los servicios: ./scripts/stop.sh"
echo "==================================================="
