#!/usr/bin/env python3
"""
Módulo: market_sentiment_analyzer.py
Función: Analizador diario de sentimiento de mercado, ingesta de noticias cripto y optimizador estratégico para Grid Bot.
Autor: Programador Senior Experto en Ciberseguridad
Descripción:
    1. Consulta el índice Fear & Greed (Alternative.me).
    2. Recolecta y sanitiza titulares RSS de CoinTelegraph y CoinDesk.
    3. Evalúa la dinámica de mercado 24h en KuCoin (KAS/USDT).
    4. Aplica un modelo cuantitativo de scoring de sentimiento ponderado.
    5. Determina el régimen de mercado y los parámetros óptimos del Grid Bot (spacing, límites, riesgo).
    6. Guarda el resultado en market_sentiment.json para consumo del dashboard.
    7. Envía un informe detallado matutino en formato HTML a Telegram.
"""

import sys
import os
import json
import re
import argparse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

# Módulo de base de datos y memoria de aprendizaje de IA
try:
    import ai_memory_db
except ImportError:
    try:
        from . import ai_memory_db
    except Exception:
        ai_memory_db = None


# Asegurar codificación UTF-8 en salida de terminal
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Credenciales de Telegram (mismo bot y chat seguro que trade_notifier)
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# Rutas de almacenamiento seguro en servidor y local
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = "data" if os.path.exists("data") else BASE_DIR
SENTIMENT_CACHE_FILE = os.path.join(LOGS_DIR, "market_sentiment.json")
GRID_CONFIG_FILE = os.path.join(LOGS_DIR, "grid_config.json")

# Diccionarios léxicos para scoring semántico financiero (sanitizado)
BULLISH_KEYWORDS = [
    "surge", "rally", "all-time high", "ath", "breakout", "inflow", "gain", "bullish",
    "accumulation", "adoption", "approval", "partnership", "pump", "record", "growth",
    "recovery", "support", "hashrate", "upgrade", "milestone", "listing"
]

BEARISH_KEYWORDS = [
    "crash", "dump", "plunge", "drop", "bearish", "fall", "outflow", "hack", "exploit",
    "lawsuit", "ban", "sec", "liquidation", "inflation", "rate hike", "vulnerable",
    "resistance", "panic", "fear", "sell-off", "investigation", "recession"
]


def sanitize_text(text, max_len=180):
    """
    Función: sanitize_text
    Sanitiza cadenas de texto externas contra inyección de HTML o prompts maliciosos.
    Elimina etiquetas y caracteres de control sospechosos.
    """
    if not text:
        return ""
    # Eliminar etiquetas HTML
    clean = re.sub(r'<[^>]*?>', '', str(text))
    # Eliminar caracteres de control no imprimibles
    clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', clean)
    # Limitar longitud
    clean = clean.strip()[:max_len]
    return clean


def fetch_fear_and_greed():
    """
    Función: fetch_fear_and_greed
    Consulta el índice oficial Fear & Greed priorizando CoinMarketCap (con sincronización directa con analysis.json y fallback a Alternative.me).
    Retorna un diccionario con score (0-100) y clasificación unificada para todo el sistema.
    """
    # 1. Intentar leer primero del análisis de mercado local generado por market_analyzer.py (CMC oficial)
    analysis_path = os.path.join(LOGS_DIR, "analysis.json")
    if os.path.exists(analysis_path):
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                fng_local = data.get("fear_and_greed")
                if fng_local and isinstance(fng_local, dict) and fng_local.get("success"):
                    return {
                        "score": int(fng_local.get("score", 50)),
                        "classification": fng_local.get("label_es") or fng_local.get("classification", "Neutral"),
                        "source": fng_local.get("source", "CoinMarketCap"),
                        "success": True
                    }
        except Exception as e_file:
            sys.stderr.write(f"[WARN] Error leyendo fear_and_greed de analysis.json: {e_file}\n")

    # 2. Si no está en analysis.json, consultar directamente CoinMarketCap API
    import time
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
            translation = {
                "Extreme fear": "Miedo Extremo",
                "Fear": "Miedo",
                "Neutral": "Neutral",
                "Greed": "Codicia",
                "Extreme greed": "Codicia Extrema"
            }
            return {
                "score": score,
                "classification": translation.get(name, name),
                "source": "CoinMarketCap",
                "success": True
            }
    except Exception as e_cmc:
        sys.stderr.write(f"[WARN] Error consultando CMC Fear & Greed API: {e_cmc}\n")

    # 3. Fallback de alta disponibilidad a Alternative.me
    url = "https://api.alternative.me/fng/?limit=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GridBot-SecurityAgent/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            item = data.get("data", [{}])[0]
            val = int(item.get("value", 50))
            classification = item.get("value_classification", "Neutral")
            translation = {
                "Extreme Fear": "Miedo Extremo",
                "Fear": "Miedo",
                "Neutral": "Neutral",
                "Greed": "Codicia",
                "Extreme Greed": "Codicia Extrema"
            }
            return {
                "score": val,
                "classification": translation.get(classification, classification),
                "source": "Alternative.me",
                "success": True
            }
    except Exception as e:
        sys.stderr.write(f"[WARN] Error consultando Fear & Greed API: {e}\n")
        return {"score": 50, "classification": "Neutral", "source": "Default", "success": False}


def fetch_rss_headlines(feed_url, source_name, max_items=5):
    """
    Función: fetch_rss_headlines
    Descarga y parsea de forma segura el feed RSS indicado, extrayendo los titulares más recientes.
    """
    headlines = []
    try:
        req = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0 (Security Bot 1.0)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            xml_data = resp.read()
            root = ET.fromstring(xml_data)
            items = root.findall("./channel/item")[:max_items]
            for it in items:
                title_el = it.find("title")
                if title_el is not None and title_el.text:
                    clean_title = sanitize_text(title_el.text)
                    if clean_title:
                        headlines.append({
                            "title": clean_title,
                            "source": source_name
                        })
    except Exception as e:
        sys.stderr.write(f"[WARN] Error leyendo feed RSS {source_name}: {e}\n")
    return headlines


def fetch_all_news():
    """
    Función: fetch_all_news
    Agrupa los titulares de CoinTelegraph y CoinDesk para el análisis de sentimiento.
    """
    all_news = []
    all_news.extend(fetch_rss_headlines("https://cointelegraph.com/rss", "CoinTelegraph", max_items=6))
    all_news.extend(fetch_rss_headlines("https://www.coindesk.com/arc/outboundfeeds/rss/", "CoinDesk", max_items=6))
    return all_news


def fetch_kucoin_kas_stats():
    """
    Función: fetch_kucoin_kas_stats
    Obtiene los datos de mercado en 24h para el par KAS-USDT directamente de KuCoin.
    """
    url = "https://api.kucoin.com/api/v1/market/stats?symbol=KAS-USDT"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GridBot-ERP/1.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("code") == "200000":
                d = res.get("data", {})
                last_price = float(d.get("last", 0.035))
                change_rate = float(d.get("changeRate", 0.0)) * 100.0
                high_24h = float(d.get("high", last_price * 1.05))
                low_24h = float(d.get("low", last_price * 0.95))
                vol_usdt = float(d.get("volValue", 0.0))
                return {
                    "last_price": last_price,
                    "change_pct_24h": change_rate,
                    "high_24h": high_24h,
                    "low_24h": low_24h,
                    "vol_usdt": vol_usdt,
                    "success": True
                }
    except Exception as e:
        sys.stderr.write(f"[WARN] Error consultando stats KuCoin KAS-USDT: {e}\n")
    return {
        "last_price": 0.0356,
        "change_pct_24h": 0.0,
        "high_24h": 0.0375,
        "low_24h": 0.0335,
        "vol_usdt": 1500000.0,
        "success": False
    }


def analyze_headline_sentiment(headlines):
    """
    Función: analyze_headline_sentiment
    Calcula un score de sentimiento léxico (0 a 100) basado en las palabras clave encontradas en los titulares.
    """
    if not headlines:
        return 50.0, []

    bullish_count = 0
    bearish_count = 0
    scored_headlines = []

    for item in headlines:
        title_lower = item["title"].lower()
        b_hits = sum(1 for kw in BULLISH_KEYWORDS if kw in title_lower)
        d_hits = sum(1 for kw in BEARISH_KEYWORDS if kw in title_lower)

        tag = "NEUTRAL"
        if b_hits > d_hits:
            tag = "BULLISH"
            bullish_count += 1
        elif d_hits > b_hits:
            tag = "BEARISH"
            bearish_count += 1

        scored_headlines.append({
            "title": item["title"],
            "source": item["source"],
            "sentiment": tag
        })

    total = len(headlines)
    net_score = 50.0 + ((bullish_count - bearish_count) / total) * 40.0
    net_score = max(5.0, min(95.0, net_score))

    return round(net_score, 1), scored_headlines


def calculate_comprehensive_sentiment(fng_data, news_score, kucoin_stats):
    """
    Función: calculate_comprehensive_sentiment
    Modela el índice de sentimiento cuantitativo combinando:
    - 40% Fear & Greed Index oficial
    - 35% Titulares de noticias (CoinDesk & CoinTelegraph)
    - 25% Dinámica de precio y volatilidad de Kaspa en 24h
    """
    fng_score = float(fng_data.get("score", 50))
    chg = kucoin_stats.get("change_pct_24h", 0.0)

    # Normalizar el cambio porcentual de Kaspa (-10% es 0, +10% es 100)
    market_score = 50.0 + (chg * 3.5)
    market_score = max(0.0, min(100.0, market_score))

    # Ponderación cuantitativa
    final_score = (fng_score * 0.40) + (news_score * 0.35) + (market_score * 0.25)
    final_score = round(max(0.0, min(100.0, final_score)), 1)

    # Clasificación en 3 Regímenes
    if final_score <= 38.0:
        regime = "FUD / Pánico Defensivo"
        badge_color = "#f85149"
        icon = "🛡️"
        recommended_preset = "conservador"
        suggested_spacing = 1.85
        risk_level = "Alto (Defensivo)"
        explanation = "Predomina el miedo en el mercado y flujo de noticias cauteloso. Se recomienda un espaciado amplio para amortiguar caídas sin agotar liquidez."
    elif final_score >= 64.0:
        regime = "Codicia / Impulso Alcista"
        badge_color = "#3fb950"
        icon = "🚀"
        recommended_preset = "equilibrado"
        suggested_spacing = 1.45
        risk_level = "Medio (Expansivo)"
        explanation = "Sentimiento alcista y compras dinámicas. Se sugiere mantener el grid activo con margen extendido para capturar máximos."
    else:
        regime = "Consolidación / Lateral Óptimo"
        badge_color = "#58a6ff"
        icon = "⚖️"
        recommended_preset = "equilibrado"
        suggested_spacing = 1.35
        risk_level = "Bajo / Neutral"
        explanation = "Escenario ideal para el Grid Bot: oscilaciones constantes en rango sin tendencia destructiva con spacing base de 1.35%."

    return {
        "final_score": final_score,
        "regime": regime,
        "badge_color": badge_color,
        "icon": icon,
        "recommended_preset": recommended_preset,
        "suggested_spacing": suggested_spacing,
        "risk_level": risk_level,
        "explanation": explanation
    }


def send_telegram_msg(text):
    """
    Función: send_telegram_msg
    Envía el mensaje en HTML a Telegram mediante HTTPS seguro y con reintento ante fallos.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except Exception as e:
        # Fallback sin parse_mode en caso de formato incompatible
        try:
            payload.pop("parse_mode", None)
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e2:
            sys.stderr.write(f"[ERROR] Error enviando reporte a Telegram: {e2}\n")
            return False


def build_telegram_daily_report(sentiment_res, fng_data, kucoin_stats, scored_headlines, recommendations=None):
    """
    Función: build_telegram_daily_report
    Genera el informe matutino profesional en HTML optimizado para Telegram,
    incluyendo el análisis macro y las recomendaciones operativas del día de la IA.
    """
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    chg_sign = "+" if kucoin_stats["change_pct_24h"] >= 0 else ""
    chg_color_icon = "🟢" if kucoin_stats["change_pct_24h"] >= 0 else "🔴"

    # Seleccionar 3 titulares más representativos
    top_news_html = ""
    for item in scored_headlines[:3]:
        s_icon = "🟢" if item["sentiment"] == "BULLISH" else ("🔴" if item["sentiment"] == "BEARISH" else "⚪")
        top_news_html += f"• {s_icon} <i>{item['title']}</i> <b>({item['source']})</b>\n"

    # Formatear recomendaciones operativas del día
    recom_html = ""
    if recommendations:
        actions = recommendations.get("actions", [])
        avoids = recommendations.get("things_to_avoid", [])
        if actions:
            recom_html += "\n💡 <b><u>Acciones Recomendadas Hoy:</u></b>\n"
            for a in actions:
                recom_html += f"  ✅ <i>{a}</i>\n"
        if avoids:
            recom_html += "\n⚠️ <b><u>Cosas a Evitar:</u></b>\n"
            for av in avoids:
                recom_html += f"  🚫 <i>{av}</i>\n"

    msg = f"""<b>🌅 INFORME MATUTINO DE MERCADO & ESTRATEGIA GRID</b>
📅 <b>Fecha:</b> {now_str}
🎯 <b>Activo:</b> KAS/USDT (Kaspa)

📊 <b><u>Termómetro de Sentimiento:</u></b>
• <b>Puntaje Cuantitativo:</b> <code>{sentiment_res['final_score']}/100</code> {sentiment_res['icon']}
• <b>Régimen:</b> <b>{sentiment_res['regime']}</b>
• <b>Fear &amp; Greed Global:</b> {fng_data['score']}/100 ({fng_data['classification']})
• <b>Dinámica KAS 24h:</b> ${kucoin_stats['last_price']:.5f} ({chg_color_icon} {chg_sign}{kucoin_stats['change_pct_24h']:.2f}%)
• <b>Rango 24h:</b> ${kucoin_stats['low_24h']:.5f} ➔ ${kucoin_stats['high_24h']:.5f}

📰 <b><u>Titulares Clave Filtrados:</u></b>
{top_news_html}
🧠 <b><u>Diagnóstico IA &amp; Recomendación Grid:</u></b>
• <b>Preset Sugerido:</b> <code>{sentiment_res['recommended_preset'].upper()}</code>
• <b>Spacing Óptimo:</b> <code>{sentiment_res['suggested_spacing']}%</code>
• <b>Nivel de Riesgo:</b> {sentiment_res['risk_level']}
• <i>{sentiment_res['explanation']}</i>
{recom_html}
⚡ <i>El bot continúa operando en KuCoin con libro en tiempo real.</i>"""

    return msg


def run_daily_analysis(send_telegram=True):
    """
    Función: run_daily_analysis
    Ejecuta el pipeline completo de recopilación, análisis de sentimiento,
    almacenamiento en caché JSON, persistencia en SQLite y notificación vía Telegram.
    """
    print("[1/5] Consultando Fear & Greed Index...")
    fng_data = fetch_fear_and_greed()

    print("[2/5] Descargando titulares RSS de CoinTelegraph y CoinDesk...")
    raw_news = fetch_all_news()
    news_score, scored_headlines = analyze_headline_sentiment(raw_news)

    print("[3/5] Consultando estadísticas 24h de KuCoin para KAS-USDT...")
    kucoin_stats = fetch_kucoin_kas_stats()

    print("[4/5] Modelando sentimiento cuantitativo y régimen de trading...")
    sentiment_res = calculate_comprehensive_sentiment(fng_data, news_score, kucoin_stats)

    report_payload = {
        "timestamp": datetime.now().isoformat(),
        "fear_and_greed": fng_data,
        "news_score": news_score,
        "headlines_analyzed": scored_headlines[:6],
        "kucoin_stats": kucoin_stats,
        "sentiment_analysis": sentiment_res
    }

    # Guardar en archivo JSON para el Dashboard y API
    try:
        with open(SENTIMENT_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(report_payload, f, indent=2, ensure_ascii=False)
        print(f"[OK] Análisis guardado en {SENTIMENT_CACHE_FILE}")
    except Exception as e:
        sys.stderr.write(f"[WARN] No se pudo guardar caché de sentimiento: {e}\n")

    # Persistencia en Base de Datos Relacional SQLite (ai_learning_memory.db)
    daily_recom = None
    if ai_memory_db is not None:
        try:
            daily_recom = ai_memory_db.save_daily_report_and_recommendations(report_payload)
            print("[OK] Memoria y recomendaciones registradas en SQLite.")
        except Exception as e_db:
            sys.stderr.write(f"[WARN] No se pudo guardar en SQLite ai_memory_db: {e_db}\n")

    # Enviar a Telegram si está habilitado
    if send_telegram:
        print("[5/5] Generando y enviando informe a Telegram...")
        telegram_text = build_telegram_daily_report(sentiment_res, fng_data, kucoin_stats, scored_headlines, recommendations=daily_recom)
        success = send_telegram_msg(telegram_text)
        if success:
            print("✅ ¡Informe diario enviado a Telegram exitosamente!")
        else:
            print("❌ Fallo al enviar informe a Telegram.")
        return success

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analizador de Sentimiento de Mercado y Noticias para Grid Bot")
    parser.add_argument("--no-telegram", action="store_true", help="Ejecutar análisis sin enviar mensaje a Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Modo prueba: imprimir reporte en consola")
    args = parser.parse_args()

    should_send = not (args.no_telegram or args.dry_run)
    run_daily_analysis(send_telegram=should_send)
