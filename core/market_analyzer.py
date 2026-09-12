"""
ANALIZADOR DE MERCADO ÓPTIMO - GRID BOT
Calcula rango geométrico óptimo y parámetros del grid
Basado en investigación de estrategias más rentables 2025-2026
Pichita Agente Hermes
"""

import os
import ccxt
import json
import numpy as np
from datetime import datetime
from config import SYMBOL, TIMEFRAME, NUM_LEVELS, GRID_SPACING_PCT, FEE_RATE, CAPITAL, LOG_DIR

def fetch_ohlcv(exchange, symbol, timeframe, limit):
    """Obtener OHLCV del exchange"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        if not ohlcv:
            raise ValueError(f"No se pudieron obtener datos de {symbol}")
        return ohlcv
    except Exception as e:
        print(f"❌ Error obteniendo OHLCV: {e}")
        raise

def calculate_rsi(prices, period=14):
    """Calcular RSI (Relative Strength Index)"""
    if len(prices) < period + 1:
        return 50.0
    
    price_changes = np.diff(prices)
    gains = np.maximum(price_changes, 0)
    losses = np.abs(np.minimum(price_changes, 0))
    
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_atr(highs, lows, closes, period=14):
    """Calcular Average True Range para medir volatilidad real"""
    if len(closes) < period + 1:
        return 0
    
    true_ranges = []
    for i in range(1, len(closes)):
        high = highs[i]
        low = lows[i]
        prev_close = closes[i-1]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        true_ranges.append(tr)
    
    return np.mean(true_ranges[-period:])

def calculate_geometric_grid(min_price, max_price, num_levels):
    """
    Calcular grid geométrico (porcentaje) óptimo.
    Mejor que aritmético para crypto porque escala con el precio.
    
    Returns:
        list: Niveles del grid
    """
    ratio = (max_price / min_price) ** (1 / num_levels)
    levels = [min_price * (ratio ** i) for i in range(num_levels + 1)]
    return levels

def fetch_cmc_fear_and_greed():
    """
    Función: fetch_cmc_fear_and_greed
    Consulta el índice oficial Fear & Greed de CoinMarketCap (con fallback a Alternative.me).
    Se ejecuta 4 veces al día (00:00, 06:00, 12:00, 18:00) sincronizado con el cron de regulación.
    """
    import time
    import urllib.request
    now = int(time.time())
    start = now - 86400 * 2
    cmc_url = f"https://api.coinmarketcap.com/data-api/v3/fear-greed/chart?start={start}&end={now}"
    try:
        req = urllib.request.Request(cmc_url, headers={"User-Agent": "Mozilla/5.0 (Security Bot CMC/1.0)"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            last_item = data.get("data", {}).get("dataList", [{}])[-1]
            score = int(last_item.get("score", 50))
            name = last_item.get("name", "Neutral")
            hist = data.get("data", {}).get("historicalValues", {})
            translation = {
                "Extreme fear": "Miedo Extremo",
                "Fear": "Miedo",
                "Neutral": "Neutral",
                "Greed": "Codicia",
                "Extreme greed": "Codicia Extrema"
            }
            return {
                "source": "CoinMarketCap",
                "score": score,
                "classification": name,
                "label_es": translation.get(name, name),
                "timestamp": last_item.get("timestamp", str(now)),
                "historical": hist,
                "success": True
            }
    except Exception as e_cmc:
        print(f"⚠️ [Aviso] Error consultando CMC Fear & Greed: {e_cmc}")

    # Fallback automático de alta disponibilidad
    try:
        alt_url = "https://api.alternative.me/fng/?limit=1"
        req = urllib.request.Request(alt_url, headers={"User-Agent": "Mozilla/5.0 (Security Bot Alt/1.0)"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            item = data.get("data", [{}])[0]
            score = int(item.get("value", 50))
            classification = item.get("value_classification", "Neutral")
            translation = {
                "Extreme Fear": "Miedo Extremo",
                "Fear": "Miedo",
                "Neutral": "Neutral",
                "Greed": "Codicia",
                "Extreme Greed": "Codicia Extrema"
            }
            return {
                "source": "Alternative.me",
                "score": score,
                "classification": classification,
                "label_es": translation.get(classification, classification),
                "timestamp": item.get("timestamp", str(now)),
                "historical": {},
                "success": True
            }
    except Exception as e_alt:
        print(f"❌ [Error] Fallo en fallback Fear & Greed: {e_alt}")
        return {
            "source": "Fallback Neutro",
            "score": 50,
            "classification": "Neutral",
            "label_es": "Neutral",
            "timestamp": str(now),
            "historical": {},
            "success": False
        }

def analyze_market(exchange):
    """
    Analizar mercado y calcular parámetros óptimos del grid
    
    Returns:
        dict: Parámetros del grid calculados
    """
    print(f"\n{'='*60}")
    print(f"📊 ANALIZANDO MERCADO: {SYMBOL}")
    print(f"{'='*60}")
    
    # Obtener datos OHLCV
    print("⏳ Obteniendo datos de mercado (72h)...")
    ohlcv = fetch_ohlcv(exchange, SYMBOL, TIMEFRAME, limit=72)
    
    # Extraer datos
    closes = np.array([c[4] for c in ohlcv])  # Precios de cierre
    highs = np.array([c[2] for c in ohlcv])    # Máximos
    lows = np.array([c[3] for c in ohlcv])     # Mínimos
    
    current_price = closes[-1]
    highest_72h = np.max(highs)
    lowest_72h = np.min(lows)
    
    # Calcular rango base
    range_pct = (highest_72h - lowest_72h) / lowest_72h * 100
    
    # Calcular RSI
    rsi = calculate_rsi(closes.tolist())
    
    # Calcular ATR (volatilidad real)
    atr = calculate_atr(highs, lows, closes)
    volatility_pct = (atr / current_price) * 100 if current_price > 0 else 0
    
    # Determinar tendencia (MA simple)
    short_ma = np.mean(closes[-7:])
    long_ma = np.mean(closes[-24:])
    trend_pct = (short_ma - long_ma) / long_ma * 100
    trend = "ALCISTA" if trend_pct > 0 else "BAJISTA"
    
    # Ingesta del Índice de Miedo y Codicia (CoinMarketCap) para el motor de aprendizaje
    print("⏳ Obteniendo Índice de Miedo y Codicia de CoinMarketCap...")
    fng_info = fetch_cmc_fear_and_greed()
    print(f"🌡️ Fear & Greed CMC: {fng_info['score']} ({fng_info['label_es']}) - Fuente: {fng_info['source']}")
    
    # Ajustar rango según RSI
    # Si RSI > 70 (sobrecompra), reducir límite superior
    # Si RSI < 30 (sobreventa), reducir límite inferior
    if rsi > 70:
        # Sobrecompra: poner el grid más abajo
        grid_min = lowest_72h * 0.98
        grid_max = current_price * (1 + range_pct * 0.3 / 100)
    elif rsi < 30:
        # Sobreventa: poner el grid más arriba
        grid_min = current_price * (1 - range_pct * 0.3 / 100)
        grid_max = highest_72h * 1.02
    else:
        # Rango neutro: usar rango completo
        grid_min = lowest_72h * 0.98
        grid_max = highest_72h * 1.02
    
    # Ajustar spacing según volatilidad
    # Más volatilidad = spacing más amplio para evitar que fees coman profit
    # Menos volatilidad = spacing más estrecho para más operaciones
    if volatility_pct < 0.3:
        adjusted_spacing = GRID_SPACING_PCT * 0.7  # Muy bajo
    elif volatility_pct < 0.8:
        adjusted_spacing = GRID_SPACING_PCT        # Normal
    elif volatility_pct < 1.5:
        adjusted_spacing = GRID_SPACING_PCT * 1.1  # Alto
    else:
        adjusted_spacing = GRID_SPACING_PCT * 1.3  # Muy alto
    
    # Calcular niveles geométricos óptimos
    # Más niveles con capital alto, menos con capital bajo
    # Con 16 USDT y spacing de 0.8%, necesitamos ~12-14 niveles
    levels = calculate_geometric_grid(grid_min, grid_max, NUM_LEVELS)
    actual_num_levels = len(levels) - 1  # Restamos 1 porque levels incluye ambos extremos
    
    # Calcular inversión por nivel
    investment_per_level = CAPITAL / actual_num_levels
    
    # Profit neto por nivel (después de fees)
    # Fee round-trip = 2 * FEE_RATE (compra + venta)
    fee_round_trip = FEE_RATE * 2
    profit_per_level_raw = adjusted_spacing / 100  # Profit bruto por nivel
    profit_per_level_net = profit_per_level_raw - fee_round_trip  # Profit neto
    
    # Asegurar que el profit neto sea positivo
    if profit_per_level_net <= 0:
        print(f"⚠️ Spacing {adjusted_spacing}% no cubre fees ({fee_round_trip*100:.1f}%)")
        print(f"   Ajustando spacing a {GRID_SPACING_PCT * 1.5:.1f}%")
        adjusted_spacing = GRID_SPACING_PCT * 1.5
        profit_per_level_net = adjusted_spacing / 100 - fee_round_trip
    
    # Ganancia neta por nivel en USDT
    profit_usd_per_level = investment_per_level * profit_per_level_net
    
    # Operaciones estimadas por día
    # Cada oscilación del rango genera ~range_pct/adjusted_spacing / 2 operaciones
    ops_per_day = max(1, int(range_pct / adjusted_spacing / 2))
    
    # Profit diario estimado (ops * profit por operación)
    daily_profit = ops_per_day * profit_usd_per_level
    
    # Stop-loss
    stop_loss = grid_min * 0.95  # 5% por debajo del mínimo del grid
    
    # Take-profit parcial
    take_profit_total = CAPITAL * 1.15  # 15% de ganancia total
    
    # Crear diccionario de resultados
    results = {
        'timestamp': datetime.now().isoformat(),
        'current_price': float(current_price),
        'highest_72h': float(highest_72h),
        'lowest_72h': float(lowest_72h),
        'range_pct': float(range_pct),
        'volatility': float(volatility_pct),
        'atr': float(atr),
        'rsi': float(rsi),
        'trend': trend,
        'trend_pct': float(trend_pct),
        'grid_min': float(grid_min),
        'grid_max': float(grid_max),
        'grid_levels': [float(l) for l in levels],
        'spacing': float(adjusted_spacing),
        'num_levels': int(actual_num_levels),
        'investment_per_level': float(investment_per_level),
        'profit_per_level_net': float(profit_per_level_net),
        'profit_usd_per_level': float(profit_usd_per_level),
        'ops_per_day': int(ops_per_day),
        'daily_profit': float(daily_profit),
        'daily_roi': float(daily_profit / CAPITAL * 100),
        'stop_loss': float(stop_loss),
        'take_profit_total': float(take_profit_total),
        'fee_round_trip_pct': float(fee_round_trip * 100),
        'fear_and_greed': fng_info,
    }
    
    # Imprimir resultados
    print(f"\n{'='*60}")
    print(f"✅ ANÁLISIS COMPLETADO")
    print(f"{'='*60}")
    print(f"💰 Precio actual: ${current_price:.6f}")
    print(f"📈 Rango 72h: {range_pct:.1f}%")
    print(f"   Mín: ${lowest_72h:.6f}")
    print(f"   Máx: ${highest_72h:.6f}")
    print(f"📊 Volatilidad (ATR): {volatility_pct:.2f}%")
    print(f"📉 RSI (14): {rsi:.1f}")
    print(f"📊 Tendencia: {trend} ({trend_pct:+.2f}%)")
    print(f"\n🎯 GRID GEOMÉTRICO ÓPTIMO:")
    print(f"   Rango: ${grid_min:.6f} - ${grid_max:.6f}")
    print(f"   Spacing: {adjusted_spacing:.2f}%")
    print(f"   Niveles: {actual_num_levels}")
    print(f"   Inversión/nivel: ${investment_per_level:.2f}")
    print(f"   Profit neto/nivel: {profit_per_level_net*100:.2f}% (${profit_usd_per_level:.4f})")
    print(f"   Fee round-trip: {fee_round_trip*100:.1f}%")
    print(f"   Ops/día estimadas: {ops_per_day}")
    print(f"   ROI diario estimado: {daily_profit/CAPITAL*100:.2f}%")
    print(f"   Stop-loss: ${stop_loss:.6f}")
    print(f"   Take-profit total: ${take_profit_total:.2f}")
    print(f"{'='*60}\n")
    
    return results

def save_analysis(results, filepath=None):
    """
    Función: save_analysis
    Guarda el análisis cuantitativo del mercado en un archivo JSON estructurado.
    """
    if filepath is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        filepath = os.path.join(LOG_DIR, "analysis.json")
    
    try:
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"📁 Análisis guardado en: {filepath}")
    except Exception as e:
        print(f"❌ Error guardando análisis: {e}")

if __name__ == "__main__":
    # Crear exchange
    exchange = ccxt.kucoin({'enableRateLimit': True, 'timeout': 30000})
    
    try:
        results = analyze_market(exchange)
        save_analysis(results)
    except Exception as e:
        print(f"❌ Error en análisis: {e}")