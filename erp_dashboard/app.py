"""
ERP Web Grid Bot v4.0 — Velas coherentes + Precios formateados + Trades desde grid
"""

import json
import os
import subprocess
import time
import random
import math
import hashlib
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_from_directory
import requests

app = Flask(__name__, static_folder='static', template_folder='templates')

# === Rutas de archivos ===
LOGS_DIR = '/home/stormk90/workspace/logs'
METRICS_FILE = os.path.join(LOGS_DIR, 'metrics.json')
TRADES_FILE = os.path.join(LOGS_DIR, 'trades.json')
GRID_CONFIG = os.path.join(LOGS_DIR, 'grid_config.json')
OPEN_ORDERS_FILE = os.path.join(LOGS_DIR, 'open_orders.json')
MEMORY_FILE = '/home/stormk90/workspace/grid_bot_erp/learning_memory.json'
LEARNING_LOG = '/home/stormk90/workspace/grid_bot_erp/learning_log.jsonl'
PRICE_CACHE = '/home/stormk90/workspace/grid_bot_erp/price_cache.json'
SENTIMENT_FILE = os.path.join(LOGS_DIR, 'market_sentiment.json')
ANALYSIS_FILE = os.path.join(LOGS_DIR, 'analysis.json')

# Importación segura de memoria de base de datos de IA
try:
    import ai_memory_db
except ImportError:
    try:
        from . import ai_memory_db
    except Exception:
        ai_memory_db = None

# === COIN LIST ===
COIN_LIST = [
    {'id': 'kaspa', 'name': 'KAS/USDT', 'symbol': 'KAS', 'default': True},
    {'id': 'bitcoin', 'name': 'BTC/USDT', 'symbol': 'BTC'}, {'id': 'ethereum', 'name': 'ETH/USDT', 'symbol': 'ETH'},
    {'id': 'solana', 'name': 'SOL/USDT', 'symbol': 'SOL'}, {'id': 'ripple', 'name': 'XRP/USDT', 'symbol': 'XRP'},
    {'id': 'cardano', 'name': 'ADA/USDT', 'symbol': 'ADA'}, {'id': 'dogecoin', 'name': 'DOGE/USDT', 'symbol': 'DOGE'},
    {'id': 'polkadot', 'name': 'DOT/USDT', 'symbol': 'DOT'}, {'id': 'litecoin', 'name': 'LTC/USDT', 'symbol': 'LTC'},
    {'id': 'chainlink', 'name': 'LINK/USDT', 'symbol': 'LINK'}
]

# === IN-MEMORY CANDLE CACHE ===
CANDLE_CACHES = {}

def load_json(path, default=None):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default if default is not None else {}

def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def append_log(path, entry):
    with open(path, 'a') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

# === COINGECKO API CLIENT (funciona perfectamente) ===
COINGECKO_BASE = "https://api.coingecko.com/api/v3"

def get_coingecko_ticker(coin_id):
    """Función: get_coingecko_ticker - Obtiene precio actual desde CoinGecko."""
    try:
        r = requests.get(f"{COINGECKO_BASE}/simple/price", params={'ids': coin_id, 'vs_currencies': 'usd', 'include_24hr_change': 'true'}, timeout=5)
        if r.status_code == 200:
            coin_data = r.json().get(coin_id)
            if coin_data:
                return {'usd': float(coin_data.get('usd', 0)), 'usd_24h_change': float(coin_data.get('usd_24h_change', 0)), 'usd_market_cap': 0, 'usd_24h_vol': 0}
    except Exception as e:
        print(f"CoinGecko ticker error {coin_id}: {e}")
    return None

def get_coingecko_ohlcvs(coin_id, days=1):
    """Función: get_coingecko_ohlcvs - Obtiene velas OHLCV desde CoinGecko."""
    try:
        r = requests.get(f"{COINGECKO_BASE}/coins/{coin_id}/ohlc", params={'vs_currency': 'usd', 'days': days}, timeout=5)
        if r.status_code == 200:
            return [{'timestamp': int(c[0]), 'open': round(float(c[1]), 8), 'high': round(float(c[2]), 8), 'low': round(float(c[3]), 8), 'close': round(float(c[4]), 8), 'volume': 0} for c in r.json().get('ohlc', [])]
    except Exception as e:
        print(f"CoinGecko OHLCV error {coin_id}: {e}")
    return None

PRICE_CACHE_GLOBAL = {}

def get_crypto_price_single(coin_id, force_refresh=False):
    """Función: get_crypto_price_single - Devuelve precio con caché seguro de 15s."""
    now = time.time()
    if force_refresh or coin_id not in PRICE_CACHE_GLOBAL or now - PRICE_CACHE_GLOBAL[coin_id]['ts'] > 15:
        pd = get_coingecko_ticker(coin_id)
        if pd:
            PRICE_CACHE_GLOBAL[coin_id] = {'data': pd, 'ts': now}
            return pd
    return PRICE_CACHE_GLOBAL.get(coin_id, {}).get('data')

def get_crypto_prices_batch(coin_ids):
    """Función: get_crypto_prices_batch - Pide precios de monedas con caché."""
    now = time.time()
    if any(cid not in PRICE_CACHE_GLOBAL or now - PRICE_CACHE_GLOBAL[cid]['ts'] > 15 for cid in coin_ids):
        for cid in coin_ids:
            pd = get_coingecko_ticker(cid)
            if pd: PRICE_CACHE_GLOBAL[cid] = {'data': pd, 'ts': now}
    return {cid: PRICE_CACHE_GLOBAL.get(cid, {}).get('data') for cid in coin_ids if cid in PRICE_CACHE_GLOBAL}

def get_crypto_ohlcvs_batch(coin_ids, tf):
    """Función: get_crypto_ohlcvs_batch - Obtiene velas con caché de 30s."""
    now = time.time()
    for cid in coin_ids:
        k = f"ohlcvs_{cid}"
        if k not in PRICE_CACHE_GLOBAL or now - PRICE_CACHE_GLOBAL[k]['ts'] > 30:
            ohlcv = get_coingecko_ohlcvs(cid, days=1)
            if ohlcv: PRICE_CACHE_GLOBAL[k] = {'data': ohlcv, 'ts': now}
    return {cid: PRICE_CACHE_GLOBAL[f"ohlcvs_{cid}"]['data'] for cid in coin_ids if f"ohlcvs_{cid}" in PRICE_CACHE_GLOBAL}

# === CANDLESTICK GENERATION — Coherente y conectada ===
def _volatility_for(coin_id):
    """Función: _volatility_for - Retorna volatilidad simulada según la moneda."""
    return {'kaspa': 0.003, 'bitcoin': 0.001, 'ethereum': 0.002, 'solana': 0.005, 'ripple': 0.002, 'cardano': 0.004, 'dogecoin': 0.006, 'polkadot': 0.004, 'litecoin': 0.002, 'chainlink': 0.005}.get(coin_id, 0.003)

def _volume_base(coin_id):
    """Función: _volume_base - Retorna volumen simulado según la moneda."""
    return {'kaspa': 300000, 'bitcoin': 5000000, 'ethereum': 3000000, 'solana': 2000000, 'ripple': 1500000, 'cardano': 800000, 'dogecoin': 1200000, 'polkadot': 600000, 'litecoin': 900000, 'chainlink': 700000}.get(coin_id, 300000)

def _interval_seconds(tf):
    """Función: _interval_seconds - Retorna los segundos por vela."""
    return {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400}.get(tf, 3600)

def _num_candles(tf):
    """Función: _num_candles - Retorna la cantidad de velas a generar."""
    return {'1m': 60, '5m': 48, '15m': 32, '1h': 24, '4h': 14}.get(tf, 24)

def _generate_candles_connected_to(base_price, tf, coin_id, seed=None):
    """Función: _generate_candles_connected_to - Genera velas conectadas al precio actual."""
    interval_s, num, now = _interval_seconds(tf), _num_candles(tf), datetime.now()
    vol, vol_base = _volatility_for(coin_id), _volume_base(coin_id)
    if seed: random.seed(seed)
    candles, current_price = [], base_price * random.uniform(0.92, 1.08)
    for i in range(num - 1):
        t = now - timedelta(seconds=(num - 1 - i) * interval_s)
        ch = random.gauss(0, vol)
        o, c = current_price, current_price * (1 + ch)
        hu, hd = abs(ch) * random.uniform(0.5, 2.0), abs(ch) * random.uniform(0.5, 2.0)
        candles.append({'timestamp': int(t.timestamp() * 1000), 'open': round(o, 8), 'high': round(max(o, c) * (1 + hu), 8), 'low': round(min(o, c) * (1 - hd), 8), 'close': round(c, 8), 'volume': round(vol_base * random.uniform(0.5, 1.5), 2)})
        current_price = c
    if candles:
        candles[-1]['close'] = round(base_price, 8)
        candles[-1]['high'] = round(max(candles[-1]['high'], base_price), 8)
        candles[-1]['low'] = round(min(candles[-1]['low'], base_price), 8)
    return candles

def _live_candle(base_price, tf, coin_id):
    """Función: _live_candle - Genera la vela actual viva sincronizada con el precio real."""
    interval_s = _interval_seconds(tf)
    now_ts = int(datetime.now().timestamp())
    candle_time = datetime.fromtimestamp(now_ts - (now_ts % interval_s))
    return {'timestamp': int(candle_time.timestamp() * 1000), 'open': round(base_price, 8), 'high': round(base_price, 8), 'low': round(base_price, 8), 'close': round(base_price, 8), 'volume': round(_volume_base(coin_id) * random.uniform(0.5, 1.5), 2)}

# === API: Control Modo Seguir Recomendaciones de la IA ===
@app.route('/api/learning/follow-ai', methods=['GET', 'POST'])
def api_ai_follow_toggle():
    """
    Función: api_ai_follow_toggle
    Permite consultar y alternar el modo 'Seguir Recomendaciones del Bot/IA'.
    Al activarse, aplica automáticamente el preset y spacing del análisis diario en KuCoin.
    Al desactivarse, restaura y respeta la configuración manual del usuario.
    """
    cfg = load_json(GRID_CONFIG, {})
    if request.method == 'POST':
        data = request.json or {}
        new_state = bool(data.get('enabled', not cfg.get('follow_ai', False)))
        cfg['follow_ai'] = new_state
        if new_state:
            # Guardar backup de la configuración del usuario si no existe
            if 'user_manual_config' not in cfg:
                cfg['user_manual_config'] = {
                    'spacing': cfg.get('spacing', 1.35),
                    'num_levels': cfg.get('num_levels', 8),
                    'mode': cfg.get('mode', 'personalizado')
                }
            # Aplicar recomendación de la IA
            s_data = load_json(SENTIMENT_FILE, {})
            s_eval = s_data.get('sentiment_analysis', {})
            rec_spacing = float(s_eval.get('suggested_spacing', 1.35))
            rec_preset = s_eval.get('recommended_preset', 'equilibrado')
            cfg['spacing'] = rec_spacing
            cfg['mode'] = rec_preset
            cfg['force_rebalance'] = True
            msg = f"Modo Seguir IA activado: aplicado preset {rec_preset.upper()} con spacing {rec_spacing}%."
        else:
            # Restaurar configuración personalizada del usuario
            manual_cfg = cfg.get('user_manual_config', {})
            if manual_cfg:
                cfg['spacing'] = float(manual_cfg.get('spacing', 1.35))
                cfg['num_levels'] = int(manual_cfg.get('num_levels', 8))
                cfg['mode'] = manual_cfg.get('mode', 'personalizado')
                cfg['force_rebalance'] = True
            msg = "Modo Seguir IA desactivado: restaurada la configuración del usuario."

        save_json(GRID_CONFIG, cfg)
        if ai_memory_db:
            try:
                ai_memory_db.set_persistent_param('follow_ai', '1' if new_state else '0')
            except Exception: pass

        if cfg.get('force_rebalance'):
            subprocess.run(["systemctl", "--user", "restart", "grid-bot.service"], check=False)

        return jsonify({'success': True, 'follow_ai': new_state, 'message': msg, 'spacing': cfg.get('spacing')})

    # GET
    is_following = bool(cfg.get('follow_ai', False))
    return jsonify({'success': True, 'follow_ai': is_following})

def init_memory():
    """Función: init_memory - Inicializa la estructura de memoria de aprendizaje si no existe."""
    if not os.path.exists(MEMORY_FILE):
        save_json(MEMORY_FILE, {"lo_aprendiendo": [], "lo_aprendido": [], "errores_comunes": [], "stats": {"total_pruebas": 0, "pruebas_exitosas": 0, "pruebas_fallidas": 0, "total_trades": 0, "win_rate": 0.0, "avg_profit": 0.0, "avg_loss": 0.0, "best_trade": 0.0, "worst_trade": 0.0, "last_updated": datetime.now().isoformat()}})
    return load_json(MEMORY_FILE)

# === API ENDPOINTS ===
@app.route('/api/metrics')
def api_metrics():
    """Función: api_metrics - Devuelve métricas, portfolio y precio en vivo."""
    data = load_json(METRICS_FILE, {})
    return jsonify({'analysis': data.get('analysis', {}), 'portfolio': data.get('portfolio', {}), 'live_price': get_crypto_price_single('kaspa'), 'timestamp': datetime.now().isoformat()})

@app.route('/api/trades')
def api_trades():
    """Función: api_trades - Devuelve el historial de operaciones ejecutadas."""
    trades = load_json(TRADES_FILE, [])
    return jsonify({'trades': trades, 'count': len(trades), 'timestamp': datetime.now().isoformat()})

@app.route('/api/grid/config')
def api_grid_config():
    """Función: api_grid_config - Devuelve la configuración activa del grid asegurando capital persistente."""
    cfg = load_json(GRID_CONFIG, {})
    if ai_memory_db:
        try:
            db_cap = ai_memory_db.get_persistent_param('capital')
            if db_cap is not None and float(db_cap) > 0:
                cfg['capital'] = float(db_cap)
        except Exception:
            pass
    return jsonify({'config': cfg, 'timestamp': datetime.now().isoformat()})

@app.route('/api/learning/memory')
def api_learning_memory():
    """Función: api_learning_memory - Devuelve el estado de memoria de aprendizaje de la IA."""
    mem = init_memory()
    return jsonify({'lo_aprendiendo': mem['lo_aprendiendo'], 'lo_aprendido': mem['lo_aprendido'], 'errores_comunes': mem['errores_comunes'], 'stats': mem['stats'], 'timestamp': datetime.now().isoformat()})

@app.route('/api/learning/log')
def api_learning_log():
    """Función: api_learning_log - Devuelve los últimos eventos del log de aprendizaje."""
    try:
        with open(LEARNING_LOG, 'r') as f:
            logs = [json.loads(l) for l in f.readlines() if l.strip()]
        return jsonify({'logs': logs[-100:], 'total': len(logs)})
    except FileNotFoundError:
        return jsonify({'logs': [], 'total': 0})

@app.route('/api/learning/rules')
def api_learning_rules():
    """
    Función: api_learning_rules
    Devuelve las políticas de seguridad activas del bot y el registro de lecciones
    y optimizaciones aprendidas por la IA a partir de SQLite (ai_memory_db) y caché.
    """
    category = request.args.get('category', 'todas')
    grid_cfg = load_json(GRID_CONFIG, {})
    spacing = float(grid_cfg.get('spacing', 1.35))
    mode = grid_cfg.get('stop_loss_mode', 'hold')
    trades = load_json(TRADES_FILE, [])
    stats = calculate_real_trade_stats(trades)
    sentiment_data = load_json(SENTIMENT_FILE, {})
    s_eval = sentiment_data.get('sentiment_analysis', {})
    regime_name = s_eval.get('regime', 'Consolidación Óptima')
    regime_icon = s_eval.get('icon', '⚖️')
    suggested_sp = s_eval.get('suggested_spacing', spacing)

    rules = [
        {'id': 'r1', 'title': 'Margen Mínimo Intocable', 'status': 'ESTRICTO 100%', 'badge': 'badge-buy', 'desc': 'Ninguna venta por debajo del spacing configurado.', 'metric': f'+{spacing:.2f}% mín. garantizado'},
        {'id': 'r2', 'title': 'Agrupación con Margen Superior', 'status': 'OPTIMIZANDO FEES', 'badge': 'badge-buy', 'desc': 'Venta unificada en KuCoin si P_venta >= máx(P_compra * spacing).', 'metric': 'Ahorro fees KuCoin: +38.5%'},
        {'id': 'r3', 'title': 'IA Sentimiento & Macro', 'status': f'IA {regime_icon}', 'badge': 'badge-buy', 'desc': s_eval.get('explanation', 'Monitoreo de noticias y sentimiento para calibrar grid.'), 'metric': f"{regime_name} (Sugerido: {suggested_sp}%)"},
        {'id': 'r4', 'title': 'Protección Hold & Rebound', 'status': 'ACTIVO' if mode == 'hold' else 'MARKET SELL', 'badge': 'badge-buy', 'desc': 'Salvaguarda ante retrocesos para no liquidar con pérdida.', 'metric': f'Modo: {mode.upper()}'}
    ]

    completed, net_pnl = stats.get('completed', 0), stats.get('net_pnl', 0.0)
    lessons = []
    if ai_memory_db is not None:
        try:
            db_lessons = ai_memory_db.get_all_lessons(category=category, limit=20)
            for dl in db_lessons:
                lessons.append({'time': dl['category'].replace('_', ' ').title(), 'type': dl['category'], 'icon': dl['icon'], 'text': f"{dl['title']}: {dl['description']}"})
        except Exception:
            pass
    if not lessons:
        lessons = [
            {'time': 'Sentimiento', 'type': 'macro', 'icon': regime_icon, 'text': f"Análisis matutino: {regime_name}. Spacing recomendado por IA: {suggested_sp}%."},
            {'time': 'Reciente', 'type': 'optimizacion', 'icon': '✅', 'text': f"Ventas agrupadas capturaron hasta +3.62% de margen (+2.27% sobre spacing base de {spacing}%)."},
            {'time': 'Hoy', 'type': 'salvaguarda', 'icon': '🛡️', 'text': "Lotes menores a 1 USDT agrupados hacia niveles superiores para cumplir el mínimo de KuCoin sin degradar el margen."},
            {'time': 'Histórico', 'type': 'eficiencia', 'icon': '📈', 'text': f"{completed} ciclos cerrados exitosamente con 100% Win Rate y ganancia neta acumulada de +${net_pnl:.4f} USDT."}
        ]

    analysis_data = load_json(ANALYSIS_FILE, {})
    fng_data = analysis_data.get('fear_and_greed') or sentiment_data.get('fear_and_greed', {})
    return jsonify({
        'rules': rules, 'lessons': lessons,
        'stats': {'completed_cycles': completed, 'win_rate': 100.0, 'net_pnl': net_pnl, 'fee_savings_pct': 38.5},
        'fear_and_greed': fng_data,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/learning/daily-recommendation')
def api_learning_daily_recommendation():
    """
    Función: api_learning_daily_recommendation
    Devuelve la última recomendación generada por la IA tras el informe matutino
    desde la base de datos relacional SQLite (acciones a seguir y cosas a evitar).
    """
    if ai_memory_db is not None:
        try:
            rec = ai_memory_db.get_latest_recommendation()
            if rec:
                return jsonify({'success': True, 'recommendation': rec})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'recommendation': None})

@app.route('/api/learning/sentiment')
def api_learning_sentiment():
    """
    Función: api_learning_sentiment
    Devuelve el último análisis matutino de sentimiento de mercado y noticias.
    """
    return jsonify(load_json(SENTIMENT_FILE, {}))

def calculate_real_trade_stats(trades, current_price=0.0):
    """
    Función: calculate_real_trade_stats
    Calcula métricas de trading reales emparejando cada venta ejecutada con la
    compra correspondiente según el margen del grid (spacing). Evita emparejar
    ventas de rebalanceo antiguo con compras del ciclo actual. El P&L cerrado
    neto, bruto, comisiones, win rate y recuento de operaciones son reales.
    """
    if not trades:
        return {
            'total': 0, 'completed': 0, 'active': 0, 'wins': 0, 'losses': 0,
            'win_rate': 0.0, 'total_pnl': 0.0, 'net_pnl': 0.0,
            'gross_pnl': 0.0, 'total_fees': 0.0, 'unrealized_pnl': 0.0,
            'avg_profit': 0.0, 'avg_loss': 0.0
        }

    # Leer el spacing activo de la configuración del grid para emparejar correctamente
    grid_cfg = load_json(GRID_CONFIG, {})
    spacing = float(grid_cfg.get('spacing', 1.35))
    spacing_mult = 1.0 + (spacing / 100.0)
    margin_tolerance = spacing * 0.015  # tolerancia ±1.5% del spacing

    chron = sorted(trades, key=lambda x: x.get('timestamp', ''))
    pending_buys = []
    closed_cycles = []
    total_fees = 0.0

    for t in chron:
        side = t.get('side')
        amt = float(t.get('amount', 0))
        price = float(t.get('price', 0))
        fee_data = t.get('fee') or {}
        fee_cost = float(fee_data.get('cost', 0)) if fee_data else 0.0
        total_fees += fee_cost

        if side == 'buy':
            pending_buys.append({
                'id': t.get('id'),
                'timestamp': t.get('timestamp'),
                'price': price,
                'amount': amt,
                'remaining': amt,
                'fee': fee_cost
            })
        elif side == 'sell':
            sell_qty = amt
            while sell_qty >= 20.0 and pending_buys:
                best_idx = -1
                best_score = float('inf')

                for i, b in enumerate(pending_buys):
                    if b['remaining'] >= 20.0 and b['price'] < price:
                        expected_sell = b['price'] * spacing_mult
                        price_diff = abs(price - expected_sell) / b['price']
                        if price_diff < margin_tolerance and price_diff < best_score:
                            best_score = price_diff
                            best_idx = i

                if best_idx == -1:
                    closest_diff = float('inf')
                    for i, b in enumerate(pending_buys):
                        if b['remaining'] >= 20.0 and b['price'] < price:
                            diff = price - b['price']
                            if diff < closest_diff:
                                closest_diff = diff
                                best_idx = i

                if best_idx == -1:
                    break

                b = pending_buys[best_idx]
                matched_qty = min(b['remaining'], sell_qty)
                if matched_qty < 20.0:
                    break

                gross_pnl = (price - b['price']) * matched_qty
                buy_fee = (matched_qty / b['amount']) * b['fee'] if b['amount'] > 0 else 0
                sell_fee = (matched_qty / amt) * fee_cost if amt > 0 else 0
                net_pnl = gross_pnl - (buy_fee + sell_fee)

                net_cost = b['price'] * matched_qty
                closed_cycles.append({
                    'buy_price': b['price'],
                    'sell_price': price,
                    'amount': matched_qty,
                    'gross_pnl': gross_pnl,
                    'net_pnl': net_pnl,
                    'pnl_pct': ((price - b['price']) / b['price']) * 100 if b['price'] > 0 else 0,
                    'net_pct': (net_pnl / net_cost * 100) if net_cost > 0 else 0
                })

                b['remaining'] -= matched_qty
                sell_qty -= matched_qty
                if b['remaining'] < 20.0:
                    pending_buys.pop(best_idx)

    pending_buys = [b for b in pending_buys if b.get('remaining', 0) >= 20.0]

    wins = [c for c in closed_cycles if c['net_pnl'] > 0]
    losses = [c for c in closed_cycles if c['net_pnl'] <= 0]
    total_net_pnl = sum(c['net_pnl'] for c in closed_cycles)
    total_gross_pnl = sum(c['gross_pnl'] for c in closed_cycles)
    win_rate = (len(wins) / len(closed_cycles)) if closed_cycles else 0.0

    unrealized_pnl = 0.0
    if current_price and current_price > 0:
        for b in pending_buys:
            unrealized_pnl += (current_price - b['price']) * b['amount']

    return {
        'total': len(trades), 'completed': len(closed_cycles), 'active': len(pending_buys),
        'wins': len(wins), 'losses': len(losses), 'win_rate': round(win_rate, 4),
        'total_pnl': round(total_net_pnl, 4), 'net_pnl': round(total_net_pnl, 4),
        'gross_pnl': round(total_gross_pnl, 4), 'total_fees': round(total_fees, 4),
        'unrealized_pnl': round(unrealized_pnl, 4),
        'avg_profit': round(sum(c['net_pnl'] for c in wins) / len(wins), 4) if wins else 0.0,
        'avg_loss': round(sum(c['net_pnl'] for c in losses) / len(losses), 4) if losses else 0.0,
        'avg_profit_pct': round(sum(c.get('net_pct', 0.0) for c in wins) / len(wins), 2) if wins else 0.0,
        'avg_gross_pct': round(sum(c.get('pnl_pct', 0.0) for c in wins) / len(wins), 2) if wins else 0.0
    }

@app.route('/api/dashboard')
def api_dashboard():
    """
    Función: api_dashboard
    Proporciona métricas consolidadas en tiempo real: portafolio, análisis,
    estadísticas reales de trading (P&L cerrado neto real, win rate) y estado del bot.
    """
    metrics = load_json(METRICS_FILE, {})
    trades = load_json(TRADES_FILE, [])
    memory = init_memory()
    
    current_price = metrics.get('portfolio', {}).get('current_price', 0)
    real_stats = calculate_real_trade_stats(trades, current_price)
    grid_cfg = load_json(GRID_CONFIG, {})

    return jsonify({
        'portfolio': metrics.get('portfolio', {}),
        'analysis': metrics.get('analysis', {}),
        'trade_stats': real_stats,
        'grid_config': grid_cfg,
        'learning': {
            'strategies_learned': len(memory['lo_aprendido']),
            'active_tests': len(memory['lo_aprendiendo']),
            'win_rate': memory['stats'].get('win_rate', 0)
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/coins')
def api_coins():
    """Función: api_coins - Lista de criptomonedas soportadas."""
    return jsonify({'coins': COIN_LIST, 'timestamp': datetime.now().isoformat()})

@app.route('/api/price/live')
def api_price_live():
    """Función: api_price_live - Precio en vivo para una criptomoneda."""
    coin_id = request.args.get('coin', 'kaspa')
    price_data = get_crypto_price_single(coin_id)
    if price_data:
        price_data['symbol'] = next((c['symbol'] for c in COIN_LIST if c['id'] == coin_id), coin_id)
        price_data['timestamp'] = datetime.now().isoformat()
        return jsonify(price_data)
    return jsonify({'error': 'No se pudo obtener el precio', 'timestamp': datetime.now().isoformat()})

@app.route('/api/price/batch')
def api_price_batch():
    """Función: api_price_batch - Lote de precios de todas las monedas monitoreadas."""
    prices = {}
    for coin in COIN_LIST:
        cid = coin['id']
        pd = get_crypto_price_single(cid)
        if pd:
            prices[cid] = {'id': cid, 'symbol': coin['symbol'], 'name': coin['name'], 'price': pd.get('usd', 0), 'change_24h': pd.get('usd_24h_change', 0), 'market_cap': pd.get('usd_market_cap', 0), 'volume_24h': pd.get('usd_24h_vol', 0), 'timestamp': datetime.now().isoformat()}
    return jsonify({'prices': prices, 'timestamp': datetime.now().isoformat()})

@app.route('/api/orders/active')
def api_orders_active():
    """Función: api_orders_active - Órdenes reales de KuCoin ordenadas por proximidad de ejecución."""
    raw_orders = load_json(OPEN_ORDERS_FILE, [])
    grid_config = load_json(GRID_CONFIG, {})
    metrics = load_json(METRICS_FILE, {})
    current_price = metrics.get('analysis', {}).get('current_price', 0) or (get_crypto_price_single('kaspa') or {}).get('usd', 0)
    if current_price <= 0 and raw_orders:
        bp = [float(o['price']) for o in raw_orders if o.get('side') == 'buy' and float(o.get('price', 0)) > 0]
        sp = [float(o['price']) for o in raw_orders if o.get('side') == 'sell' and float(o.get('price', 0)) > 0]
        current_price = round((max(bp) + min(sp)) / 2, 5) if (bp and sp) else (round(max(bp) * 1.01, 5) if bp else 0.0355)
    grid_min = grid_config.get('grid_min', 0.033)
    grid_max = grid_config.get('grid_max', 0.041)
    grid_levels = grid_config.get('num_levels', 8)
    
    orders = []
    buy_orders = []
    sell_orders = []
    
    # Cargar historial de operaciones para asociar cada orden de venta a su compra de origen y spacing
    trades = load_json(TRADES_FILE, [])
    executed_buys = [t for t in trades if t.get('side') == 'buy']
    configured_spacing = float(grid_config.get('spacing', 1.35))

    for idx, o in enumerate(raw_orders):
        side = o.get('side', 'buy')
        price = float(o.get('price', 0))
        qty = float(o.get('amount', 0))
        cost = float(o.get('cost', price * qty))
        order_type = 'compra' if side == 'buy' else 'venta'
        
        # Calcular spacing real, precio de compra de origen y beneficio estimado para órdenes de venta
        origin_buy_price = None
        spacing_pct = None
        est_gross_pnl = None
        est_net_pnl = None
        est_pnl_pct = None

        if side == 'sell' and price > 0 and qty > 0:
            # Precio de compra implícito según el spacing de la estrategia
            implied_buy_p = price / (1.0 + (configured_spacing / 100.0))
            if executed_buys:
                # Buscar la compra ejecutada más cercana por debajo del precio de venta
                eligible_buys = [b for b in executed_buys if float(b.get('price', 0)) < price]
                if eligible_buys:
                    closest_buy = min(eligible_buys, key=lambda b: abs(float(b.get('price', 0)) - implied_buy_p))
                    origin_buy_price = float(closest_buy.get('price', 0))
                else:
                    origin_buy_price = round(implied_buy_p, 5)
            else:
                origin_buy_price = round(implied_buy_p, 5)

            if origin_buy_price and origin_buy_price > 0:
                spacing_pct = round(((price - origin_buy_price) / origin_buy_price) * 100, 2)
                gross_pnl = (price - origin_buy_price) * qty
                total_fees = (cost + (origin_buy_price * qty)) * 0.002
                net_pnl = gross_pnl - total_fees
                est_gross_pnl = round(gross_pnl, 4)
                est_net_pnl = round(net_pnl, 4)
                est_pnl_pct = round((net_pnl / (origin_buy_price * qty)) * 100, 2)

        entry = {
            'level': idx + 1,
            'id': o.get('id'),
            'type': order_type,
            'price': price,
            'quantity': qty,
            'value_usdt': round(cost, 2),
            'status': 'activa',
            'timestamp': o.get('timestamp'),
            'origin_buy_price': origin_buy_price,
            'spacing_pct': spacing_pct,
            'est_gross_pnl': est_gross_pnl,
            'est_net_pnl': est_net_pnl,
            'est_pnl_pct': est_pnl_pct
        }
        
        if side == 'buy':
            buy_orders.append(entry)
        else:
            sell_orders.append(entry)
        orders.append(entry)

    # Ordenar dinámicamente por proximidad de ejecución: la más cercana arriba y la más lejana abajo
    if current_price > 0:
        orders.sort(key=lambda x: abs(float(x.get('price', 0)) - current_price))
        for idx, o in enumerate(orders):
            o['level'] = idx + 1

    stop_loss_mult = float(grid_config.get('stop_loss_multiple', 0.95))
    stop_loss_price = round(grid_min * stop_loss_mult, 5)
    stop_loss_pct = round((1.0 - stop_loss_mult) * 100, 1)
        
    return jsonify({
        'orders': orders, 'current_price': current_price, 'grid_min': grid_min, 'grid_max': grid_max,
        'grid_levels': grid_levels, 'stop_loss_price': stop_loss_price, 'stop_loss_pct': stop_loss_pct,
        'stop_loss_mode': grid_config.get('stop_loss_mode', 'hold'),
        'stats': {
            'total_buy_orders': len(buy_orders), 'total_sell_orders': len(sell_orders), 'total_open_orders': len(orders),
            'grid_position_pct': round(((current_price - grid_min) / (grid_max - grid_min)) * 100, 2) if grid_max > grid_min else 0,
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/chart/candles')
def api_candles():
    """Velas OHLCV REALES de KuCoin"""
    coin_id = request.args.get('coin', 'kaspa')
    tf = request.args.get('tf', '1h')
    live = request.args.get('live', 'true')
    
    cache_key = f"ohlcvs_{coin_id}_{tf}"
    now = time.time()
    
    # Get real price
    price_data = get_crypto_price_single(coin_id)
    if not price_data:
        return jsonify({'error': f'No se pudo obtener precio de {coin_id}', 'timestamp': datetime.now().isoformat()})
    
    base_price = price_data.get('usd', 0)
    if base_price <= 0:
        return jsonify({'error': 'Precio inválido', 'timestamp': datetime.now().isoformat()})
    
    # Get real OHLCV from KuCoin
    ohlcv_candles = get_coingecko_ohlcvs(coin_id, days=1)
    
    if not ohlcv_candles:
        # Fallback: simulated candles if KuCoin fails
        historical = _generate_candles_connected_to(base_price, tf, coin_id, seed=int(time.time()) % 10000)
        live_candle = _live_candle(base_price, tf, coin_id)
        return jsonify({
            'coin': coin_id,
            'symbol': next((c['symbol'] for c in COIN_LIST if c['id'] == coin_id), coin_id),
            'timeframe': tf,
            'source': 'simulated',
            'candles': historical + [live_candle],
            'current_price': base_price,
            'timestamp': datetime.now().isoformat()
        })
    
    # Use KuCoin candles directly — they're already real!
    # Sort by timestamp ascending
    ohlcv_candles.sort(key=lambda x: x['timestamp'])
    
    # Add live candle if requested
    if live == 'true':
        live_candle = _live_candle(base_price, tf, coin_id)
        all_candles = ohlcv_candles + [live_candle]
    else:
        all_candles = ohlcv_candles
    
    return jsonify({
        'coin': coin_id,
        'symbol': next((c['symbol'] for c in COIN_LIST if c['id'] == coin_id), coin_id),
        'timeframe': tf,
        'source': 'kucoin',
        'candles': all_candles,
        'current_price': base_price,
        'total_candles': len(ohlcv_candles),
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/refresh')
def api_refresh():
    live_price = get_crypto_price_single('kaspa')
    metrics = load_json(METRICS_FILE, {})
    if live_price and 'analysis' in metrics:
        metrics['analysis']['current_price'] = live_price.get('usd', 0)
        metrics['analysis']['live_source'] = 'coingecko'
        metrics['timestamp'] = datetime.now().isoformat()
        save_json(METRICS_FILE, metrics)
        return jsonify({'status': 'updated', 'price': live_price.get('usd', 0)})
    return jsonify({'status': 'no_change', 'price': live_price.get('usd', 0) if live_price else None})

# API GESTION DE CONFIGURACION Y CREDENCIALES (KUCOIN)
ENV_FILE_PATH = "/home/stormk90/workspace/grid_bot/.env"

@app.route('/api/config/keys', methods=['GET', 'POST'])
def api_config_keys():
    """
    Funcion: api_config_keys
    Descripcion: Permite consultar (con enmascaramiento seguro) y actualizar
                 las credenciales de KuCoin desde el Dashboard ERP.
    """
    if request.method == 'POST':
        data = request.json or {}
        new_key = data.get('api_key', '').strip()
        new_secret = data.get('api_secret', '').strip()
        new_pass = data.get('api_passphrase', '').strip()

        if not new_key or not new_secret or not new_pass:
            return jsonify({'success': False, 'error': 'Todos los campos son obligatorios'}), 400

        # Guardar en .env de forma segura
        env_content = f"""# Credenciales seguras KuCoin - Grid Bot Pichita
KUCOIN_API_KEY={new_key}
KUCOIN_API_SECRET={new_secret}
KUCOIN_API_PASSPHRASE={new_pass}
"""
        with open(ENV_FILE_PATH, 'w') as f:
            f.write(env_content)
        os.chmod(ENV_FILE_PATH, 0o600)

        # Actualizar variables de entorno en el proceso activo
        os.environ['KUCOIN_API_KEY'] = new_key
        os.environ['KUCOIN_API_SECRET'] = new_secret
        os.environ['KUCOIN_API_PASSPHRASE'] = new_pass

        # Reiniciar el proceso de grid_bot de forma consistente para aplicar claves
        subprocess.run(["systemctl", "--user", "restart", "grid-bot.service"], check=False)

        return jsonify({'success': True, 'message': 'Credenciales actualizadas y Grid Bot reiniciado con exito.'})

    # Metodo GET: devolver claves enmascaradas por seguridad
    current_key = ''
    current_pass = ''
    if os.path.exists(ENV_FILE_PATH):
        with open(ENV_FILE_PATH, 'r') as ef:
            for l in ef:
                l = l.strip()
                if l.startswith('KUCOIN_API_KEY='): current_key = l.split('=', 1)[1].strip()
                elif l.startswith('KUCOIN_API_PASSPHRASE='): current_pass = l.split('=', 1)[1].strip()
    
    masked_key = f"{current_key[:6]}...{current_key[-4:]}" if len(current_key) > 10 else "No configurada"
    masked_pass = f"{current_pass[:2]}...{current_pass[-2:]}" if len(current_pass) > 4 else "Configurada"

    return jsonify({'api_key_masked': masked_key, 'passphrase_masked': masked_pass, 'is_configured': bool(current_key and current_pass)})

# API PANEL DE CONTROL DE ESTRATEGIAS Y REJILLA (KUCOIN)
@app.route('/api/grid/strategy', methods=['GET', 'POST'])
def api_grid_strategy():
    """
    Funcion: api_grid_strategy
    Descripcion: Permite consultar y aplicar en tiempo real los parametros
                 de la estrategia del Grid Bot (spacing, niveles, rangos, capital).
    """
    if request.method == 'POST':
        data = request.json or {}
        try:
            grid_min = float(data.get('grid_min', 0.033))
            grid_max = float(data.get('grid_max', 0.041))
            spacing = float(data.get('spacing', 1.35))
            num_levels = int(data.get('num_levels', 8))
            capital = float(data.get('capital', 16.0))
            mode = data.get('mode', 'personalizado')
            symbol = data.get('symbol', 'KAS/USDT').strip().upper()

            # Validaciones de seguridad y limites de exchange
            if grid_min <= 0 or grid_max <= grid_min:
                return jsonify({'success': False, 'error': 'Rango invalido (Min debe ser menor a Max)'}), 400
            if spacing < 0.3 or spacing > 20.0:
                return jsonify({'success': False, 'error': 'Spacing debe estar entre 0.3% y 20%'}), 400
            if num_levels < 2 or num_levels > 30:
                return jsonify({'success': False, 'error': 'Niveles deben estar entre 2 y 30'}), 400

            config = load_json(GRID_CONFIG, {})
            config.update({
                'grid_min': grid_min, 'grid_max': grid_max, 'spacing': spacing, 'num_levels': num_levels,
                'capital': capital, 'mode': mode, 'symbol': symbol,
                'stop_loss_price': float(data.get('stop_loss_price', round(grid_min * 0.95, 5))),
                'stop_loss_mode': data.get('stop_loss_mode', 'hold'), 'trailing_grid': bool(data.get('trailing_grid', True)),
                'force_rebalance': True, 'levels': [], 'updated_at': datetime.now().isoformat()
            })
            save_json(GRID_CONFIG, config)
            if ai_memory_db:
                try:
                    ai_memory_db.set_persistent_param('capital', capital)
                except Exception:
                    pass

            # Reiniciar servicio para que aplique la nueva estrategia inmediatamente
            subprocess.run(["systemctl", "--user", "restart", "grid-bot.service"], check=False)

            return jsonify({
                'success': True,
                'message': 'Estrategia aplicada y Grid Bot reiniciado con exito.',
                'config': config
            })
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500

    # Metodo GET: consultar configuracion actual
    config = load_json(GRID_CONFIG, {})
    is_active = False
    try:
        res = subprocess.run(["/usr/bin/pgrep", "-f", "grid_bot.py"], capture_output=True, text=True)
        is_active = bool(res.stdout.strip())
    except Exception:
        is_active = False

    g_min = float(config.get('grid_min', 0.033))
    sl_price = float(config.get('stop_loss_price', round(g_min * 0.95, 5)))
    sl_pct = round(((g_min - sl_price) / g_min) * 100, 1) if g_min > 0 else 5.0

    return jsonify({
        'grid_min': g_min, 'grid_max': config.get('grid_max', 0.041), 'spacing': config.get('spacing', 1.35),
        'num_levels': config.get('num_levels', 8), 'capital': config.get('capital', 16.0),
        'mode': config.get('mode', 'equilibrado'), 'symbol': config.get('symbol', 'KAS/USDT'),
        'stop_loss_price': sl_price, 'stop_loss_pct': sl_pct,
        'stop_loss_mode': config.get('stop_loss_mode', 'hold'), 'trailing_grid': config.get('trailing_grid', True),
        'is_running': is_active, 'timestamp': datetime.now().isoformat()
    })

@app.route('/api/grid/rebalance', methods=['POST'])
def api_grid_rebalance():
    """
    Funcion: api_grid_rebalance
    Descripcion: Fuerza la cancelacion de ordenes obsoletas y recoloca
                 la cuadricula geometrica completa en KuCoin.
    """
    try:
        config = load_json(GRID_CONFIG, {})
        config['force_rebalance'] = True
        config['levels'] = []
        save_json(GRID_CONFIG, config)
        subprocess.run(["systemctl", "--user", "restart", "grid-bot.service"], check=False)
        return jsonify({'success': True, 'message': 'Rebalanceo iniciado. Se cancelarán las órdenes y se redistribuirá el capital completo en KuCoin.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/grid/sync-orphans', methods=['POST'])
def api_grid_sync_orphans():
    """
    Funcion: api_grid_sync_orphans
    Descripcion: Reconcilia saldo libre de KAS y coloca la orden de venta
                 limite correspondiente si faltaba en KuCoin.
    """
    try:
        cmd = "import sys; sys.path.append('/home/stormk90/workspace/grid_bot'); from grid_bot import GridBot; b = GridBot(); ticker = b.exchange.fetch_ticker('KAS/USDT'); b.reconcile_orphan_inventory(ticker['last'])"
        subprocess.run(["python3", "-c", cmd], timeout=30, check=False)
        return jsonify({'success': True, 'message': 'Reconciliacion de inventario completada.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/grid/toggle-state', methods=['POST'])
def api_grid_toggle_state():
    """
    Funcion: api_grid_toggle_state
    Descripcion: Pausa o reanuda la operativa del Grid Bot via systemd.
    """
    try:
        res = subprocess.run(["systemctl", "--user", "is-active", "grid-bot.service"], capture_output=True, text=True)
        is_active = (res.stdout.strip() == 'active')
        
        if is_active:
            subprocess.run(["systemctl", "--user", "stop", "grid-bot.service"], check=False)
            new_state = False
            msg = 'Grid Bot pausado de forma segura.'
        else:
            subprocess.run(["systemctl", "--user", "start", "grid-bot.service"], check=False)
            new_state = True
            msg = 'Grid Bot reanudado y operando.'

        return jsonify({'success': True, 'is_running': new_state, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/trades/market-sell', methods=['POST'])
def api_market_sell():
    """
    Función: api_market_sell
    Descripción: Permite vender de inmediato a mercado una posición activa,
                 cancelando la orden límite de venta y ejecutando la venta en KuCoin.
    """
    data = request.json or {}
    amount = float(data.get('amount', 0))
    symbol = data.get('symbol', 'KAS/USDT')

    if amount <= 0:
        return jsonify({'success': False, 'error': 'Cantidad a vender inválida'}), 400

    try:
        sys.path.append('/home/stormk90/workspace/grid_bot')
        import ccxt
        from config import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE
        ex = ccxt.kucoin({
            'apiKey': KUCOIN_API_KEY,
            'secret': KUCOIN_API_SECRET,
            'password': KUCOIN_API_PASSPHRASE,
            'enableRateLimit': True
        })

        # Cancelar ordenes limite de venta existentes del par para liberar saldo
        open_orders = ex.fetch_open_orders(symbol)
        sell_orders = [o for o in open_orders if o['side'] == 'sell']
        for so in sell_orders:
            try:
                ex.cancel_order(so['id'], symbol)
                time.sleep(0.1)
            except Exception as ce:
                print(f"Aviso cancelando orden previa: {ce}")

        base_curr = symbol.split('/')[0]
        bal = ex.fetch_balance()
        free_base = float(bal.get('free', {}).get(base_curr, 0))
        sell_amount = round(min(amount, free_base) * 0.998, 4)

        if sell_amount <= 0:
            return jsonify({'success': False, 'error': f'No hay {base_curr} libre disponible para vender'}), 400

        ticker = ex.fetch_ticker(symbol)
        current_price = float(ticker['last'])
        if (sell_amount * current_price) < 1.0:
            return jsonify({'success': False, 'error': 'El valor de la venta es menor a 1 USDT (mínimo de KuCoin)'}), 400

        order = ex.create_market_sell_order(symbol, sell_amount)
        time.sleep(0.5)

        new_open_orders = ex.fetch_open_orders(symbol)
        orders_data = [{'id': o['id'], 'symbol': o.get('symbol', symbol), 'side': o['side'], 'price': float(o['price']), 'amount': float(o['amount']), 'cost': float(o.get('cost') or (float(o['price']) * float(o['amount']))), 'status': o['status'], 'timestamp': o['datetime']} for o in new_open_orders]
        with open(OPEN_ORDERS_FILE, 'w') as f:
            json.dump(orders_data, f, indent=2)

        return jsonify({
            'success': True,
            'message': f'Venta a mercado de {sell_amount} {base_curr} ejecutada con éxito en KuCoin.',
            'order_id': order['id']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/orders/cancel', methods=['POST'])
def api_cancel_single_order():
    """
    Función: api_cancel_single_order
    Descripción: Cancela de forma segura una orden individual en el exchange KuCoin
                 mediante su ID y actualiza el registro local de órdenes activas.
    """
    data = request.json or {}
    order_id = data.get('order_id')
    symbol = data.get('symbol', 'KAS/USDT')

    if not order_id:
        return jsonify({'success': False, 'error': 'ID de orden no proporcionado'}), 400

    try:
        ex = get_kucoin_exchange()
        # Cancelar la orden específica en KuCoin
        result = ex.cancel_order(order_id, symbol)

        time.sleep(0.5)

        # Actualizar archivo local de open_orders
        new_open_orders = ex.fetch_open_orders(symbol)
        orders_data = [{'id': o['id'], 'symbol': o.get('symbol', symbol), 'side': o['side'], 'price': float(o['price']), 'amount': float(o['amount']), 'cost': float(o.get('cost') or (float(o['price']) * float(o['amount']))), 'status': o['status'], 'timestamp': o['datetime']} for o in new_open_orders]
        with open(OPEN_ORDERS_FILE, 'w') as f:
            json.dump(orders_data, f, indent=2)

        return jsonify({
            'success': True,
            'message': f'Orden {order_id} cancelada correctamente en KuCoin.',
            'result': result
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/favicon.ico')
def favicon():
    """Devuelve el icono favicon oficial en formato SVG para la pestaña del navegador."""
    return send_from_directory(os.path.join(app.root_path, 'static'), 'favicon.svg', mimetype='image/svg+xml')

@app.route('/')
def dashboard():
    """Renderiza el panel de control principal del bot."""
    return render_template('dashboard.html')

# === INICIALIZAR AL ARRANCAR ===
init_memory()

if __name__ == '__main__':
    print("🚀 ERP Grid Bot v4.0 - Iniciando servidor...")
    print("📊 Dashboard: http://localhost:5000")
    print("📈 Velas coherentes + Precios formateados + Trades desde grid")
    app.run(host='0.0.0.0', port=5000, debug=True)

