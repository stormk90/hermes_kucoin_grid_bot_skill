#!/usr/bin/env bash
set -e

echo "==================================================="
echo "🚀 Instalador Automático: Hermes Grid Bot & ERP Web"
echo "==================================================="

if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 no está instalado. Instálalo e intenta de nuevo."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual aislado (venv)..."
    python3 -m venv venv
fi

echo "📥 Instalando dependencias de requirements.txt..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

mkdir -p data

if [ ! -f ".env" ]; then
    echo "⚙️ Creando archivo .env a partir de .env.example..."
    cp .env.example .env
    chmod 600 .env
    echo "⚠️ ATENCIÓN: Edita el archivo .env con tus credenciales de KuCoin antes de iniciar."
else
    echo "✅ Archivo .env existente detectado."
fi

echo ""
echo "✅ Instalación completada con éxito."
echo "Para iniciar el bot y el Dashboard ERP: ./scripts/start.sh"
echo "==================================================="
