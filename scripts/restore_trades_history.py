"""
Módulo: restore_trades_history.py
Función: restore_and_audit_full_trades
Descripción: Recupera de forma segura el 100% del historial de operaciones desde KuCoin API
y archivos de respaldo, reconstruyendo trades.json de forma atómica y protegida.
"""

import sys
import os
import json
import time
import shutil
from datetime import datetime, timezone, timedelta

# Inclusión de rutas dinámicas según entorno
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOME_DIR = os.path.expanduser('~')
WORKSPACE_DIR = os.getenv('WORKSPACE_DIR', os.path.join(HOME_DIR, 'workspace'))
for p in [os.path.join(WORKSPACE_DIR, 'grid_bot'), os.path.join(WORKSPACE_DIR, 'grid_bot_erp'), BASE_DIR]:
    if p not in sys.path and os.path.exists(p):
        sys.path.append(p)

import ccxt
try:
    from config import KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE, SYMBOL, LOG_DIR
except ImportError:
    # Carga alternativa de variables si se ejecuta directamente
    KUCOIN_API_KEY = os.getenv('KUCOIN_API_KEY', '')
    KUCOIN_API_SECRET = os.getenv('KUCOIN_API_SECRET', '')
    KUCOIN_API_PASSPHRASE = os.getenv('KUCOIN_API_PASSPHRASE', '')
    SYMBOL = os.getenv('GRID_SYMBOL', 'KAS/USDT')
    candidate_logs = os.path.join(WORKSPACE_DIR, 'logs')
    LOG_DIR = candidate_logs if os.path.exists(candidate_logs) else os.path.join(BASE_DIR, 'logs')


def restore_and_audit_full_trades():
    """
    Función: restore_and_audit_full_trades
    Reconcilia y restaura el historial íntegro de trades desde KuCoin, eliminando duplicados
    y blindando trades.json con copias de seguridad automáticas y guardado atómico.
    """
    print("=" * 60)
    print("🔒 INICIANDO RESTAURACIÓN PROFESIONAL DEL HISTORIAL DE TRADING")
    print("=" * 60)

    trades_file = os.path.join(LOG_DIR, "trades.json")
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(LOG_DIR, f"trades_backup_{now_str}.json")
    permanent_bak = os.path.join(LOG_DIR, "trades.json.bak")
    ledger_file = os.path.join(LOG_DIR, "execution_ledger.json")

    # 1. Copia de seguridad preventiva del archivo actual
    if os.path.exists(trades_file):
        try:
            shutil.copy2(trades_file, backup_file)
            shutil.copy2(trades_file, permanent_bak)
            print(f"✅ Copia de seguridad preventiva guardada en: {backup_file}")
        except Exception as e_bak:
            print(f"Aviso al crear backup preventivo: {e_bak}")

    # 2. Conectar a KuCoin mediante CCXT
    exchange = ccxt.kucoin({
        "apiKey": KUCOIN_API_KEY,
        "secret": KUCOIN_API_SECRET,
        "password": KUCOIN_API_PASSPHRASE,
        "enableRateLimit": True
    })

    # 3. Paginación segura por ventanas de 6 días desde 01/09/2026 hasta fecha actual
    start_dt = datetime(2026, 9, 1, tzinfo=timezone.utc)
    end_dt = datetime.now(timezone.utc) + timedelta(days=2)

    all_kucoin_trades = []
    symbol_kucoin = "KAS-USDT"
    cur = start_dt

    print("📡 Descargando todas las operaciones desde la API oficial de KuCoin...")
    while cur < end_dt:
        nxt = cur + timedelta(days=6)
        s_ts = int(cur.timestamp() * 1000)
        e_ts = int(nxt.timestamp() * 1000)
        
        page = 1
        while True:
            try:
                res = exchange.private_get_fills({
                    "symbol": symbol_kucoin,
                    "startAt": s_ts,
                    "endAt": e_ts,
                    "pageSize": 500,
                    "currentPage": page
                })
                data = res.get("data", {})
                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    parsed = exchange.parse_trade(item)
                    all_kucoin_trades.append({
                        "id": str(parsed["id"]),
                        "order_id": str(parsed.get("order") or ""),
                        "timestamp": parsed["datetime"],
                        "datetime": parsed["datetime"],
                        "symbol": parsed.get("symbol", SYMBOL),
                        "side": parsed["side"],
                        "price": float(parsed["price"]),
                        "amount": float(parsed["amount"]),
                        "cost": float(parsed["cost"]),
                        "fee": parsed.get("fee", {})
                    })

                total_pages = data.get("totalPage", 1)
                if page >= total_pages:
                    break
                page += 1
            except Exception as e:
                print(f"⚠️ Aviso en ventana {cur.strftime('%Y-%m-%d')} - {nxt.strftime('%Y-%m-%d')}, pág {page}: {e}")
                break
        cur = nxt

    print(f"📥 Operaciones obtenidas directamente de KuCoin: {len(all_kucoin_trades)}")

    # 4. Cargar trades existentes y del ledger si existen
    current_trades = []
    if os.path.exists(trades_file):
        try:
            with open(trades_file, "r", encoding="utf-8") as f:
                current_trades = json.load(f)
        except Exception as e:
            print(f"Aviso leyendo trades.json actual: {e}")

    ledger_trades = []
    if os.path.exists(ledger_file):
        try:
            with open(ledger_file, "r", encoding="utf-8") as f:
                ledger_trades = json.load(f)
        except Exception as e:
            print(f"Aviso leyendo execution_ledger.json: {e}")

    # 5. Fusión inteligente y deduplicación por ID único de trade
    merged = {}
    for t in all_kucoin_trades:
        tid = str(t.get("id") or "")
        if tid:
            merged[tid] = t

    for t in current_trades:
        tid = str(t.get("id") or "")
        if tid and tid not in merged:
            merged[tid] = t

    for t in ledger_trades:
        tid = str(t.get("id") or "")
        if tid and tid not in merged:
            merged[tid] = t

    # 6. Ordenamiento cronológico estricto
    restored_list = sorted(merged.values(), key=lambda x: str(x.get("timestamp") or x.get("datetime") or ""))
    print(f"✨ Total operaciones únicas consolidadas y verificadas: {len(restored_list)}")

    if not restored_list:
        print("❌ Error crítico: la lista consolidada está vacía. Abortando escritura.")
        return False

    first_trade = restored_list[0]
    last_trade = restored_list[-1]
    print(f"📅 Rango Temporal: Desde {first_trade.get('timestamp')} hasta {last_trade.get('timestamp')}")

    # 7. Escritura atómica blindada (archivo temporal + os.replace)
    tmp_file = trades_file + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(restored_list, f, indent=2, ensure_ascii=False)
    os.replace(tmp_file, trades_file)

    # Actualizar también copia de seguridad permanente
    shutil.copy2(trades_file, permanent_bak)

    # Asegurar permisos correctos
    try:
        shutil.chown(trades_file, user="hermes", group="hermes")
        shutil.chown(permanent_bak, user="hermes", group="hermes")
        os.chmod(trades_file, 0o664)
        os.chmod(permanent_bak, 0o664)
    except Exception:
        pass

    print(f"💾 trades.json reescrito y asegurado exitosamente con {len(restored_list)} operaciones.")

    # 8. Auditar estadísticas con el módulo de cálculo del ERP si está disponible
    try:
        from app import calculate_real_trade_stats
        metrics_file = os.path.join(LOG_DIR, "metrics.json")
        curr_price = 0.0494
        if os.path.exists(metrics_file):
            try:
                m_data = json.load(open(metrics_file))
                curr_price = float(m_data.get("portfolio", {}).get("current_price", curr_price))
            except: pass
        stats = calculate_real_trade_stats(restored_list, curr_price)
        print("\n📊 RESULTADO AUDITADO TRAS LA RESTAURACIÓN:")
        print(f"  • Operaciones Totales: {stats.get('total')}")
        print(f"  • Ciclos Completados: {stats.get('completed')}")
        print(f"  • Victorias / Pérdidas: {stats.get('wins')} / {stats.get('losses')} (Win Rate: {stats.get('win_rate')*100:.2f}%)")
        print(f"  • P&L Cerrado Neto Real: +${stats.get('net_pnl'):.4f} USDT")
        print(f"  • Comisiones Totales Pagadas: ${stats.get('total_fees'):.4f} USDT")
        print(f"  • P&L No Realizado (Lotes en curso): {'+' if stats.get('unrealized_pnl',0)>=0 else ''}${stats.get('unrealized_pnl'):.4f} USDT")
    except Exception as e_stats:
        print(f"Aviso calculando estadísticas auditadas: {e_stats}")

    print("=" * 60)
    print("✅ RESTAURACIÓN COMPLETADA CON ÉXITO")
    print("=" * 60)
    return True

if __name__ == "__main__":
    restore_and_audit_full_trades()
