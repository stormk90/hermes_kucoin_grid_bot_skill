"""
Configuración centralizada y segura del Grid Bot y Motor de IA.
Carga credenciales desde el archivo local .env sin exponer secretos.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Cargar variables de entorno desde .env local si existe
env_path = BASE_DIR / '.env'
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f_env:
        for line in f_env:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

# Credenciales de KuCoin
KUCOIN_API_KEY = os.getenv('KUCOIN_API_KEY', '')
KUCOIN_API_SECRET = os.getenv('KUCOIN_API_SECRET', '')
KUCOIN_API_PASSPHRASE = os.getenv('KUCOIN_API_PASSPHRASE', '')

# Parámetros operativos
SYMBOL = os.getenv('SYMBOL', 'KAS/USDT')
TIMEFRAME = os.getenv('TIMEFRAME', '1h')
CAPITAL = float(os.getenv('CAPITAL', '16.00'))
GRID_SPACING_PCT = float(os.getenv('GRID_SPACING_PCT', '1.35'))
NUM_GRID_LEVELS = int(os.getenv('NUM_GRID_LEVELS', '8'))
NUM_LEVELS = NUM_GRID_LEVELS
FEE_RATE = 0.001

# Notificaciones Telegram (Opcional)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

# Rutas de almacenamiento de datos operacionales (en subcarpeta data/)
LOG_DIR = str(BASE_DIR / 'data')
os.makedirs(LOG_DIR, exist_ok=True)

TRADE_LOG = os.path.join(LOG_DIR, 'trades.json')
METRICS_FILE = os.path.join(LOG_DIR, 'metrics.json')
STATUS_FILE = os.path.join(LOG_DIR, 'status.json')
OPEN_ORDERS_FILE = os.path.join(LOG_DIR, 'open_orders.json')
GRID_CONFIG_FILE = os.path.join(LOG_DIR, 'grid_config.json')
SENTIMENT_FILE = os.path.join(LOG_DIR, 'market_sentiment.json')
ANALYSIS_FILE = os.path.join(LOG_DIR, 'analysis.json')

# Salvaguardas
SCAN_INTERVAL = 30
REBALANCE_INTERVAL = 21600
STOP_LOSS_MULTIPLE = 0.95
TAKE_PROFIT_PCT = 0.15
MAX_DAILY_LOSS = -1.5
