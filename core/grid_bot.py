"""
GRID BOT PROFESIONAL MULTI-PAR - KUCOIN
Soporte dinámico para cualquier par spot (KAS/USDT, BTC/USDT, ETH/USDT, SOL/USDT).
Reconciliación automática de inventario, respeto de mínimos y control desde ERP.
"""

import ccxt, json, time, sys, os, subprocess, math
from datetime import datetime
try:
    from market_analyzer import analyze_market, save_analysis
except ImportError:
    analyze_market, save_analysis = None, None
from config import (
    KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE, SYMBOL, CAPITAL, GRID_SPACING_PCT,
    NUM_LEVELS, FEE_RATE, LOG_DIR, TRADE_LOG, METRICS_FILE, STATUS_FILE, OPEN_ORDERS_FILE,
    SCAN_INTERVAL, REBALANCE_INTERVAL, STOP_LOSS_MULTIPLE, TAKE_PROFIT_PCT, MAX_DAILY_LOSS
)
from ai_memory_db import set_persistent_param, get_persistent_param

def send_telegram(message):
    """Función: send_telegram - Envía notificaciones críticas hacia la IA Pichita."""
    try:
        if any(k in message.upper() for k in ("STOP-LOSS", "TAKE-PROFIT", "CRITICO")):
            reporter = os.path.expanduser("~/.hermes/ia_crypto_reporter.py")
            if os.path.exists(reporter):
                subprocess.Popen(["python3", reporter, "--tipo", "alerta", "--alerta", message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return True

    except Exception as e:
        print(f"Error al notificar a la IA: {e}")
        return False

class GridBot:
    """
    Clase: GridBot
    Controlador principal de la estrategia de Grid Trading continuo con soporte multi-par.
    """
    def __init__(self):
        self.exchange = ccxt.kucoin({
            'enableRateLimit': True,
            'timeout': 30000,
            'apiKey': KUCOIN_API_KEY,
            'secret': KUCOIN_API_SECRET,
            'password': KUCOIN_API_PASSPHRASE,
        })
        self.running, self.symbol = False, SYMBOL
        self.grid_min, self.grid_max, self.spacing = 0.033, 0.041, GRID_SPACING_PCT
        self.levels, self.trades, self.known_trade_ids = [], [], set()
        self.last_rebalance, self.stop_loss_mode, self.stop_loss_price = None, 'hold', None
        self.capital, self.max_order_usdt, self.reserve_usdt = float(CAPITAL), 50.0, 0.0
        self.trailing_grid, self.trailing_down, self.max_active_buys = True, True, 6
        self.take_profit_notified = False
        self.load_trades()
        self.load_config()

    def get_base_quote(self):
        """
        Función: get_base_quote
        Retorna la moneda base y cotizada (ej. 'KAS' y 'USDT').
        """
        parts = self.symbol.split('/')
        return parts[0], parts[1] if len(parts) > 1 else 'USDT'

    def load_trades(self):
        """
        Función: load_trades
        Carga el historial de ejecuciones previas de forma resiliente con soporte de respaldo.
        """
        bak = TRADE_LOG + ".bak"
        loaded = []
        if os.path.exists(TRADE_LOG):
            try:
                with open(TRADE_LOG, 'r', encoding='utf-8') as f: loaded = json.load(f)
            except Exception as e: print(f"Aviso leyendo trades: {e}")
        if not loaded and os.path.exists(bak):
            try:
                with open(bak, 'r', encoding='utf-8') as f: loaded = json.load(f)
                print(f"🔄 Recuperados {len(loaded)} trades desde backup.")
            except Exception: pass
        self.trades = loaded if isinstance(loaded, list) else []
        self.known_trade_ids = {str(t.get('id')) for t in self.trades if t.get('id')}

    def get_pending_buy_inventory(self):
        """
        Función: get_pending_buy_inventory
        Calcula los lotes de compra reales pendientes mediante el módulo desacoplado LotTracker,
        guardando un snapshot atómico en lot_inventory.json para auditoría y ERP.
        """
        try:
            self.load_trades()
            base_curr, quote_curr = self.get_base_quote()
            bal = self.exchange.fetch_balance()
            total_base = float(bal.get('total', {}).get(base_curr, 0))
            if total_base <= 0.5:
                return []

            try:
                from lot_tracker import LotTracker
                tracker = LotTracker(LOG_DIR, self.symbol)
                inv = tracker.sync_from_trades(self.trades, total_base, self.spacing)
                return inv.get('lots', [])
            except Exception as e_track:
                print(f"[AVISO] Fallback local calculando lotes: {e_track}")
                chron = sorted(self.trades, key=lambda x: x.get('timestamp', ''))
                return [{
                    'id': t.get('id'), 'price': float(t.get('price', 0)),
                    'remaining': float(t.get('amount', 0)), 'amount': float(t.get('amount', 0)),
                    'timestamp': t.get('timestamp')
                } for t in chron if t.get('symbol') == self.symbol and t.get('side') == 'buy']
        except Exception as e:
            print(f"Error calculando inventario de compras: {e}")
            return []

    def load_config(self):
        """
        Función: load_config
        Carga la configuración activa del grid desde SQLite y grid_config.json preservando el capital real.
        """
        config_file = os.path.join(LOG_DIR, 'grid_config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                self.symbol = config.get('symbol', self.symbol)
                self.grid_min = float(config.get('grid_min', self.grid_min))
                self.grid_max = float(config.get('grid_max', self.grid_max))
                self.spacing = float(config.get('spacing', self.spacing))
                self.levels = config.get('levels', [])
                self.num_levels = int(config.get('num_levels', NUM_LEVELS))
                self.last_rebalance = config.get('last_rebalance')
                self.stop_loss_mode = config.get('stop_loss_mode', 'hold')
                self.stop_loss_price = config.get('stop_loss_price')

                saved_cap = config.get('capital')
                if saved_cap and float(saved_cap) > 0:
                    self.capital = float(saved_cap)
                    try: set_persistent_param('capital', float(saved_cap))
                    except Exception: pass
                else:
                    db_cap = get_persistent_param('capital')
                    self.capital = float(db_cap) if (db_cap and float(db_cap) > 0) else float(CAPITAL)

                self.max_order_usdt = float(config.get('max_order_usdt', getattr(self, 'max_order_usdt', 50.0)))
                self.reserve_usdt = float(config.get('reserve_usdt', getattr(self, 'reserve_usdt', 0.0)))
                target_buys = max(4, min(12, int(self.capital // max(1.0, self.max_order_usdt))))
                self.max_active_buys = int(config.get('max_active_buys', target_buys))
                self.trailing_grid = bool(config.get('trailing_grid', True))
                self.trailing_down = bool(config.get('trailing_down', True))
                self.trailing_down_floor = float(config.get('trailing_down_floor', round(self.grid_min * 0.90, 5)))
                self.force_rebalance = bool(config.get('force_rebalance', False))
                print(f"Configuración cargada: Par={self.symbol}, Spacing={self.spacing}%, Capital={self.capital} USDT, MaxOrden={self.max_order_usdt} USDT, Reserva={self.reserve_usdt} USDT, Trailing={self.trailing_grid}")
            except Exception as e:
                print(f"Aviso al cargar configuración previa: {e}")

    def save_config(self, config):
        """
        Función: save_config
        Persiste los parámetros del grid en grid_config.json y en la base de datos SQLite.
        """
        try:
            config_file = os.path.join(LOG_DIR, 'grid_config.json')
            config['symbol'] = self.symbol
            if hasattr(self, 'capital') and self.capital and self.capital > 0:
                config['capital'] = float(self.capital)
            config['max_order_usdt'] = float(getattr(self, 'max_order_usdt', 50.0))
            config['reserve_usdt'] = float(getattr(self, 'reserve_usdt', 0.0))
            config['max_active_buys'] = int(getattr(self, 'max_active_buys', 6))
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            try:
                if hasattr(self, 'capital') and self.capital and self.capital > 0:
                    set_persistent_param('capital', float(self.capital))
                set_persistent_param('max_order_usdt', float(self.max_order_usdt))
                set_persistent_param('reserve_usdt', float(self.reserve_usdt))
            except Exception: pass
        except Exception as e:
            print(f"Error guardando config: {e}")

    def save_trades(self):
        """
        Función: save_trades
        Guarda las operaciones de forma atómica fusionando con disco para evitar pérdidas.
        """
        try:
            if not self.trades: return
            disk_trades = []
            if os.path.exists(TRADE_LOG):
                try:
                    with open(TRADE_LOG, 'r', encoding='utf-8') as f: disk_trades = json.load(f)
                except Exception: pass
            merged = {str(t.get('id')): t for t in disk_trades if t.get('id')}
            for t in self.trades:
                if t.get('id'): merged[str(t.get('id'))] = t
            self.trades = sorted(merged.values(), key=lambda x: str(x.get('timestamp') or x.get('datetime') or ''))
            self.known_trade_ids = set(merged.keys())
            tmp_file = TRADE_LOG + ".tmp"
            bak_file = TRADE_LOG + ".bak"
            with open(tmp_file, 'w', encoding='utf-8') as f: json.dump(self.trades, f, indent=2, ensure_ascii=False)
            os.replace(tmp_file, TRADE_LOG)
            import shutil; shutil.copy2(TRADE_LOG, bak_file)
        except Exception as e:
            print(f"Error guardando trades de forma atómica: {e}")

    def sync_open_orders_file(self, open_orders):
        """
        Función: sync_open_orders_file
        Exporta las órdenes vivas en KuCoin para el consumo en tiempo real del ERP.
        """
        try:
            orders_data = [{
                'id': o.get('id'), 'symbol': o.get('symbol', self.symbol), 'side': o.get('side'),
                'price': float(o.get('price', 0)), 'amount': float(o.get('amount', 0)),
                'cost': float(o.get('cost') or (float(o.get('price', 0)) * float(o.get('amount', 0)))),
                'status': o.get('status', 'open'), 'timestamp': o.get('datetime')
            } for o in open_orders]
            with open(OPEN_ORDERS_FILE, 'w') as f:
                json.dump(orders_data, f, indent=2)
        except Exception as e:
            print(f"Error sincronizando open_orders.json: {e}")

    def cancel_old_orders(self, side=None):
        """
        Función: cancel_old_orders
        Cancela las órdenes abiertas del par activo en KuCoin. Si side está especificado ('buy' o 'sell'),
        únicamente cancela las órdenes de dicho lado, protegiendo las ventas límite existentes.
        """
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            if side:
                open_orders = [o for o in open_orders if o.get('side') == side]
            if open_orders:
                print(f"Cancelando {len(open_orders)} órdenes abiertas ({side or 'todas'}) en {self.symbol}...")
                for order in open_orders:
                    try:
                        self.exchange.cancel_order(order['id'], self.symbol)
                        time.sleep(0.1)
                    except Exception as e:
                        print(f"Error cancelando orden {order['id']}: {e}")
                return True
        except Exception as e:
            print(f"Error cancelando órdenes generales: {e}")
        return False

    def setup_grid(self, analysis_results):
        """
        Función: setup_grid
        Calcula los niveles de la rejilla geométrica para el par seleccionado.
        """
        self.grid_min = float(analysis_results.get('grid_min', self.grid_min))
        self.grid_max = float(analysis_results.get('grid_max', self.grid_max))
        spacing = float(analysis_results.get('spacing', self.spacing))
        grid_levels = int(analysis_results.get('grid_levels', NUM_LEVELS))

        self.levels = []
        mult = 1.0 + (spacing / 100.0)
        current_price = self.grid_min

        # Determinar precisión de redondeo según la escala de precio
        decimals = 5 if current_price < 1.0 else (2 if current_price > 50 else 4)

        idx = 0
        while current_price <= self.grid_max and idx < 25:
            self.levels.append({
                'level': idx,
                'price': round(current_price, decimals),
                'type': 'buy' if idx < (grid_levels // 2) else 'sell',
                'filled': False,
                'order_id': None
            })
            current_price = current_price * mult
            idx += 1

        config = {
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'grid_min': self.grid_min,
            'grid_max': self.grid_max,
            'spacing': spacing,
            'num_levels': len(self.levels),
            'levels': self.levels,
            'last_rebalance': datetime.now().isoformat(),
            'capital': float(self.capital) if (hasattr(self, 'capital') and self.capital and self.capital > 0) else float(CAPITAL),
            'investment_per_level': (float(self.capital) if (hasattr(self, 'capital') and self.capital and self.capital > 0) else float(CAPITAL)) / max(1, len(self.levels)),
        }
        self.save_config(config)
        self.last_rebalance = datetime.now().isoformat()
        return config

    def place_grid_orders(self):
        """
        Función: place_grid_orders
        Coloca órdenes iniciales de compra y venta respetando el límite mínimo de 1.0 USDT de KuCoin.
        """
        print(f"Colocando órdenes del Grid en KuCoin para {self.symbol}...")
        base_curr, quote_curr = self.get_base_quote()
        balance = self.exchange.fetch_balance()
        free_quote = float(balance.get('free', {}).get(quote_curr, 0))
        free_base = float(balance.get('free', {}).get(base_curr, 0))
        ticker = self.exchange.fetch_ticker(self.symbol)
        current_price = float(ticker['last'])

        print(f"Balances libres: {quote_curr}={free_quote:.2f}, {base_curr}={free_base:.4f} | Precio: ${current_price}")

        buy_levels = [l for l in self.levels if l['price'] < current_price]
        sell_levels = [l for l in self.levels if l['price'] > current_price]
        
        buy_levels.sort(key=lambda x: x['price'], reverse=True)
        sell_levels.sort(key=lambda x: x['price'])

        placed = 0
        failed = 0

        # 1. Órdenes de COMPRA (Protección anti-duplicados: 1 posición por nivel de precio)
        open_orders_existing = self.exchange.fetch_open_orders(self.symbol)
        existing_buy_prices = [float(o['price']) for o in open_orders_existing if o['side'] == 'buy']
        existing_sell_prices = [float(o['price']) for o in open_orders_existing if o['side'] == 'sell']
        pending_buys = self.get_pending_buy_inventory()
        pending_buy_prices = [float(b['price']) for b in pending_buys if b.get('remaining', 0) > 0.01]

        # Filtrar niveles donde ya exista orden BUY, orden SELL abierta o posición pendiente de venta
        filtered_buy_levels = []
        for lvl in buy_levels:
            lp = lvl['price']
            has_buy = any(abs(lp - ep) / lp < 0.003 for ep in existing_buy_prices)
            has_sell = any(abs(lp - sp) / lp < 0.003 for sp in existing_sell_prices)
            has_hold = any(abs(lp - pp) / lp < 0.003 for pp in pending_buy_prices)
            if not has_buy and not has_sell and not has_hold:
                filtered_buy_levels.append(lvl)
            else:
                print(f"   [NIVEL BLOQUEADO] Compra en ${lp} omitida para evitar duplicados en el mismo precio.")

        min_cost = 1.05
        # Salvaguarda: Reserva intocable, tope de capital y techo exclusivo para compras (nunca limita ventas)
        reserve = getattr(self, 'reserve_usdt', 0.0)
        usable_quote = max(0.0, free_quote - reserve)
        max_capital_allowed = float(self.capital) if hasattr(self, 'capital') and self.capital > 0 else usable_quote
        quote_to_allocate = min(usable_quote, max_capital_allowed)
        max_order_cap = getattr(self, 'max_order_usdt', 50.0)

        print(f"Capital: ${max_capital_allowed:.2f} | Libre: ${free_quote:.2f} | Reserva: ${reserve:.2f} | Presupuesto: ${quote_to_allocate:.2f} | Max/Compra: ${max_order_cap:.2f}")

        max_active_buys = getattr(self, 'max_active_buys', 6)
        if filtered_buy_levels and quote_to_allocate >= min_cost:
            effective_buy_levels = filtered_buy_levels[:max_active_buys]
            quote_per_order = min(quote_to_allocate / len(effective_buy_levels), max_order_cap)

            for lvl in effective_buy_levels:
                price = lvl['price']
                amount = round((quote_per_order / price) * 0.998, 4)
                cost = amount * price
                if 1.0 <= cost <= (max_order_cap * 1.02):
                    try:
                        order = self.exchange.create_limit_buy_order(self.symbol, amount, price)
                        lvl['order_id'] = order['id']
                        placed += 1
                        print(f"   [BUY] Nivel {lvl['level']}: {amount} {base_curr} @ ${price} (${cost:.2f} USDT)")
                    except Exception as e:
                        print(f"   [ERROR BUY] @ ${price}: {e}")
                        failed += 1

        # 2. Órdenes de VENTA (Protección estricta: cada venta calculada 100% desde su precio de compra + spacing)
        pending_buys = self.get_pending_buy_inventory()
        spacing_mult = 1.0 + (self.spacing / 100.0)
        decimals = 5 if current_price < 1.0 else (2 if current_price > 50 else 4)

        if pending_buys and free_base > 0:
            # Venta estricta 1:1 por lote individual: Prohibido acumular o fusionar órdenes
            orders_to_place = []

            # Inspeccionar órdenes de venta ya abiertas en KuCoin para no duplicar
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            existing_sells = [o for o in open_orders if o.get('side') == 'sell']

            for pb in pending_buys:
                kas_lot = pb['remaining']
                # REGLA DE ORO: El precio de venta se deriva EXCLUSIVAMENTE del precio de compra del lote
                target_p = round(pb['price'] * spacing_mult, decimals)

                # Si ya existe orden de venta viva en KuCoin a este precio objetivo, no duplicarla
                has_existing = any(abs(float(o.get('price', 0)) - target_p) / target_p < 0.0005 for o in existing_sells)
                if has_existing:
                    continue

                val = kas_lot * target_p
                if val >= 1.0: # Cumple mínimo KuCoin
                    orders_to_place.append({'amount': kas_lot, 'price': target_p})

            # Ordenar por precio ascendente para colocar primero las ventas más próximas al precio actual
            orders_to_place.sort(key=lambda o: o['price'])
            available_kas = free_base

            for o in orders_to_place:
                if available_kas <= 0.5:
                    break
                # Asignación de lote completo 1:1 íntegro: exactamente los mismos que entran por los que salen
                lot_qty = min(o['amount'], available_kas)
                amt = round(lot_qty, 4)
                prc = o['price']
                if amt * prc >= 1.0:
                    try:
                        order = self.exchange.create_limit_sell_order(self.symbol, amt, prc)
                        placed += 1
                        available_kas -= lot_qty
                        print(f"   [SELL 1:1 ÍNTEGRO] {amt} {base_curr} @ ${prc} (Margen: +{self.spacing}%)")
                    except Exception as e:
                        print(f"   [ERROR SELL 1:1] @ ${prc}: {e}")
                        failed += 1
        elif free_base * current_price >= 1.0 and self.levels:
            # Saldo huérfano sin compra previa: anclar al nivel geométrico de rejilla superior más cercano
            higher_levels = [lvl['price'] for lvl in self.levels if lvl['price'] > current_price]
            sell_price = higher_levels[0] if higher_levels else round(self.grid_max, decimals)
            sell_amount = round(free_base, 4)
            if sell_amount * sell_price >= 1.0:
                try:
                    order = self.exchange.create_limit_sell_order(self.symbol, sell_amount, sell_price)
                    placed += 1
                    print(f"   [SELL REJILLA BASE] {sell_amount} {base_curr} @ ${sell_price}")
                except Exception as e:
                    print(f"   [ERROR SELL REJILLA BASE]: {e}")
                    failed += 1

        open_orders = self.exchange.fetch_open_orders(self.symbol)
        self.sync_open_orders_file(open_orders)
        print(f"Resumen Rejilla {self.symbol}: {placed} colocadas. Abiertas totales: {len(open_orders)}")
        return placed, failed

    def reconcile_orphan_inventory(self, current_price):
        """
        Función: reconcile_orphan_inventory
        Audita el inventario de ventas en KuCoin: normaliza órdenes partidas cancelándolas
        para colocar la orden 1:1 exacta, y reconcilia saldo libre con órdenes límite respaldadas por lotes.
        """
        try:
            base_curr, quote_curr = self.get_base_quote()
            spacing_mult = 1.0 + (self.spacing / 100.0)
            decimals = 5 if current_price < 1.0 else (2 if current_price > 50 else 4)

            open_orders = self.exchange.fetch_open_orders(self.symbol)
            sell_orders = [o for o in open_orders if o.get('side') == 'sell']
            pending_buys = self.get_pending_buy_inventory()

            # Polvo huérfano residual no divisible por ser menor al mínimo de $1 de KuCoin (ej. ~4 KAS)
            balance = self.exchange.fetch_balance()
            free_base = float(balance.get('free', {}).get(base_curr, 0))
            orphan_dust = free_base if (0.5 < free_base and (free_base * current_price) < 1.0) else 0.0

            # 1. Normalización autónoma: unificar órdenes partidas o añadir polvo huérfano al nivel superior
            need_balance_refresh = False
            if pending_buys:
                sorted_buys = sorted(pending_buys, key=lambda x: x['price'])
                highest_buy_id = sorted_buys[-1]['id'] if sorted_buys else None

                for pb in sorted_buys:
                    target_p = round(pb['price'] * spacing_mult, decimals)
                    matching_sells = [o for o in sell_orders if abs(float(o.get('price', 0)) - target_p) / target_p < 0.0005]
                    exact_lot = round(pb['remaining'], 4)
                    is_highest = (pb['id'] == highest_buy_id)
                    target_lot = math.floor((exact_lot + orphan_dust) * 10000) / 10000 if (is_highest and orphan_dust > 0) else exact_lot

                    # Evaluación de ajuste respetando regla 1:1 y absorción de polvo en nivel superior
                    curr_amount = float(matching_sells[0].get('amount', 0)) if len(matching_sells) == 1 else 0.0
                    should_adjust = False

                    if len(matching_sells) > 1:
                        # Órdenes partidas en el mismo nivel: unificar en una sola orden íntegra
                        should_adjust = True
                    elif len(matching_sells) == 1:
                        if is_highest:
                            # Nivel superior: mantiene el polvo absorbido sin cancelaciones innecesarias
                            if curr_amount < exact_lot - 0.5:
                                should_adjust = True
                            elif orphan_dust > 0.5 and abs(curr_amount - (exact_lot + orphan_dust)) > 0.5:
                                should_adjust = True
                        else:
                            # Niveles normales 1:1: verificación estricta de coincidencia con el lote
                            if abs(curr_amount - exact_lot) > 0.5:
                                should_adjust = True

                    if should_adjust:
                        print(f"   [BOT AUTÓNOMO 1:1] Ajustando orden en ${target_p} (Objetivo: {target_lot} KAS). Normalizando...")
                        for so in matching_sells:
                            try:
                                self.exchange.cancel_order(so['id'], self.symbol)
                                time.sleep(0.1)
                                need_balance_refresh = True
                            except Exception as ce:
                                print(f"   Aviso cancelando orden {so['id']}: {ce}")

            # 2. Refrescar balance libre y órdenes vivas si hubo cancelaciones
            if need_balance_refresh:
                balance = self.exchange.fetch_balance()
                free_base = float(balance.get('free', {}).get(base_curr, 0))
                open_orders = self.exchange.fetch_open_orders(self.symbol)
                sell_orders = [o for o in open_orders if o.get('side') == 'sell']

            if free_base <= 0.5:
                return False

            placed_any = False
            remaining_free = free_base

            if pending_buys:
                sorted_buys = sorted(pending_buys, key=lambda x: x['price'])
                highest_buy_id = sorted_buys[-1]['id'] if sorted_buys else None

                for pb in sorted_buys:
                    target_p = round(pb['price'] * spacing_mult, decimals)
                    has_order = any(abs(float(o.get('price', 0)) - target_p) / target_p < 0.0005 for o in sell_orders)
                    if has_order:
                        continue

                    is_highest = (pb['id'] == highest_buy_id)
                    lot_amount = math.floor(remaining_free * 10000) / 10000 if is_highest else math.floor(min(pb['remaining'], remaining_free) * 10000) / 10000

                    if lot_amount * target_p >= 1.0:
                        try:
                            order = self.exchange.create_limit_sell_order(self.symbol, lot_amount, target_p)
                            dust_msg = " [incluye polvo huérfano liquidado]" if is_highest and lot_amount > pb['remaining'] else ""
                            print(f"   [RECONCILIACIÓN 1:1 ÍNTEGRA] Venta de {lot_amount} {base_curr} @ ${target_p}{dust_msg} [ID: {order['id']}]")
                            remaining_free -= lot_amount
                            placed_any = True
                        except Exception as e:
                            print(f"   Aviso colocando venta individual @ ${target_p}: {e}")

            if placed_any:
                self.sync_open_orders_file(self.exchange.fetch_open_orders(self.symbol))
                return True
        except Exception as e:
            print(f"Aviso en reconcile_orphan_inventory: {e}")
        return False

    def reconcile_quote_inventory(self, current_price):
        """
        Función: reconcile_quote_inventory
        Coloca compras en niveles desatendidos respetando reserva intocable y tope por orden.
        """
        try:
            base_curr, quote_curr = self.get_base_quote()
            balance = self.exchange.fetch_balance()
            free_quote = float(balance.get('free', {}).get(quote_curr, 0))
            reserve = getattr(self, 'reserve_usdt', 0.0)
            usable_quote = max(0.0, free_quote - reserve)
            max_order_cap = getattr(self, 'max_order_usdt', 50.0)
            min_order_cost = max(15.0, max_order_cap * 0.4)
            if usable_quote < min_order_cost:
                return False

            open_orders = self.exchange.fetch_open_orders(self.symbol)
            ex_buys = [float(o['price']) for o in open_orders if o['side'] == 'buy']
            ex_sells = [float(o['price']) for o in open_orders if o['side'] == 'sell']
            deployed_buy_cost = sum(float(o.get('cost') or (float(o['price']) * float(o['amount']))) for o in open_orders if o['side'] == 'buy')
            p_buys = [float(b['price']) for b in self.get_pending_buy_inventory() if b.get('remaining', 0) > 0.01]

            buy_levels = sorted([l for l in self.levels if l['price'] < current_price * 0.998], key=lambda x: x['price'], reverse=True)
            empty_levels = [l for l in buy_levels if not (any(abs(l['price'] - p) / l['price'] < 0.003 for p in ex_buys + ex_sells + p_buys))]
            if not empty_levels:
                return False

            max_active_buys = getattr(self, 'max_active_buys', 6)
            if len(ex_buys) >= max_active_buys:
                return False
            available_slots = max_active_buys - len(ex_buys)

            cap_limit = float(self.capital) if hasattr(self, 'capital') and self.capital > 0 else usable_quote
            effective_budget = min(usable_quote, max(0.0, cap_limit - deployed_buy_cost))
            if effective_budget < min_order_cost:
                return False

            max_orders = min(available_slots, max(1, int(effective_budget // min_order_cost)))
            selected = empty_levels[:max_orders]
            if not selected:
                return False
            quote_per_order = min(effective_budget / len(selected), max_order_cap)
            if quote_per_order < min_order_cost:
                return False

            placed_any = False
            for lvl in selected:
                price = lvl['price']
                amount = round((quote_per_order / price) * 0.998, 4)
                cost = amount * price
                if min_order_cost <= cost <= (max_order_cap * 1.02):
                    try:
                        order = self.exchange.create_limit_buy_order(self.symbol, amount, price)
                        print(f"   [RECONCILIACIÓN BUY] {amount} {base_curr} @ ${price} (${cost:.2f} USDT) [ID: {order['id']}]")
                        placed_any = True
                    except Exception as e:
                        print(f"   Aviso compra en ${price}: {e}")

            if placed_any:
                self.sync_open_orders_file(self.exchange.fetch_open_orders(self.symbol))
                return True
        except Exception as e:
            print(f"Aviso en reconcile_quote_inventory: {e}")
        return False

    def monitor_and_cycle(self):
        """
        Función: monitor_and_cycle
        Detección continua de ejecuciones mediante fetch_my_trades y colocación
        inmediata de la contra-orden correspondiente con ganancia mínima garantizada.
        """
        try:
            recent_trades = sorted(self.exchange.fetch_my_trades(self.symbol, limit=50), key=lambda x: x.get('timestamp', 0))
            new_trades_detected = 0
            unseen = []

            for t in recent_trades:
                tid = t.get('id')
                if tid and tid not in self.known_trade_ids:
                    self.known_trade_ids.add(tid)
                    trade_record = {
                        'id': tid,
                        'order_id': t.get('order'),
                        'timestamp': t.get('datetime'),
                        'symbol': t.get('symbol', self.symbol),
                        'side': t.get('side'),
                        'price': float(t.get('price', 0)),
                        'amount': float(t.get('amount', 0)),
                        'cost': float(t.get('cost', 0)),
                        'fee': t.get('fee', {})
                    }
                    self.trades.append(trade_record)
                    unseen.append(trade_record)
                    new_trades_detected += 1

            if not unseen:
                return 0

            # Agrupación de ejecuciones parciales por (side, order_id)
            aggregated = {}
            for tr in unseen:
                key = (tr['side'], tr.get('order_id') or str(round(tr['price'], 4)))
                if key not in aggregated:
                    aggregated[key] = {
                        'side': tr['side'],
                        'order_id': tr.get('order_id'),
                        'total_amount': 0.0,
                        'total_cost': 0.0,
                        'count': 0,
                        'sample_price': tr['price']
                    }
                aggregated[key]['total_amount'] += tr['amount']
                aggregated[key]['total_cost'] += tr['cost']
                aggregated[key]['count'] += 1

            decimals = 5 if self.symbol.startswith('KAS') else 4
            spacing_mult = 1.0 + (self.spacing / 100.0)

            for key, agg in aggregated.items():
                side = agg['side']
                amount = round(agg['total_amount'], 4)
                cost = round(agg['total_cost'], 4)
                price = round(cost / amount, decimals) if amount > 0 else agg['sample_price']
                fills_txt = f" ({agg['count']} parciales agrupados)" if agg['count'] > 1 else ""
                print(f"⚡ TRADE CONSOLIDADO EN KUCOIN ({self.symbol}): {side.upper()} {amount} @ ${price}{fills_txt}")

                # Disparo único a Telegram consolidado (1 mensaje por orden, nunca por fill parcial)
                try:
                    notif_bin = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_notifier.py")
                    if os.path.exists(notif_bin):
                        subprocess.Popen([
                            "python3", notif_bin,
                            "--side", side,
                            "--price", str(price),
                            "--amount", str(amount),
                            "--symbol", self.symbol
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                except Exception as err_notif:

                    print(f"   -> Aviso disparando notificador Telegram: {err_notif}")

                if side == 'buy':
                    # REGLA 1:1 ESTRICTA: Cada compra coloca su propia contra-orden de venta por el 100% íntegro de lo comprado
                    sell_price = round(price * spacing_mult, decimals)
                    sell_amount = round(amount, 4)
                    cost_sell = sell_amount * sell_price
                    if cost_sell >= 1.0:
                        try:
                            new_order = self.exchange.create_limit_sell_order(self.symbol, sell_amount, sell_price)
                            print(f"   -> Contra-orden SELL 1:1 colocada: {sell_amount} @ ${sell_price} [ID: {new_order['id']}]")
                        except Exception as e:
                            print(f"   -> Error colocando venta 1:1: {e}")
                elif side == 'sell':
                    buy_price = round(price / spacing_mult, decimals)
                    open_orders_now = self.exchange.fetch_open_orders(self.symbol)
                    existing_buys = [float(o['price']) for o in open_orders_now if o['side'] == 'buy']
                    if any(abs(buy_price - ep) / buy_price < 0.003 for ep in existing_buys):
                        print(f"   -> [OMITIDO] Ya existe orden BUY activa en nivel ${buy_price}")
                    else:
                        base_curr, quote_curr = self.get_base_quote()
                        balance = self.exchange.fetch_balance()
                        free_quote = float(balance.get('free', {}).get(quote_curr, 0))
                        reserve = getattr(self, 'reserve_usdt', 0.0)
                        usable_quote = max(0.0, free_quote - reserve)
                        max_order_cap = getattr(self, 'max_order_usdt', 50.0)
                        min_order_cost = max(15.0, max_order_cap * 0.4)
                        if usable_quote >= min_order_cost:
                            target_cost = min(max_order_cap, usable_quote)
                            buy_amount = round((target_cost / buy_price) * 0.998, 4)
                            cost_buy = buy_amount * buy_price
                            try:
                                new_order = self.exchange.create_limit_buy_order(self.symbol, buy_amount, buy_price)
                                print(f"   -> Contra-orden BUY colocada: {buy_amount} @ ${buy_price} (${cost_buy:.2f} USDT) [ID: {new_order['id']}]")
                            except Exception as e:
                                print(f"   -> Error colocando contra-orden BUY: {e}")

            if new_trades_detected > 0:
                self.save_trades()

            open_orders = self.exchange.fetch_open_orders(self.symbol)
            self.sync_open_orders_file(open_orders)
            return new_trades_detected

        except Exception as e:
            print(f"Error en monitor_and_cycle: {e}")
            return 0

    def check_trailing_grid(self, current_price):
        """
        Función: check_trailing_grid
        Rejilla Dinámica Adaptativa Bidireccional con Ventana Deslizante Continua:
        - Trailing Up: Si el precio sube por encima de la compra más alta más de un spacing,
          cancela la compra más alejada/profunda (aliviando liquidez congelada al -10%),
          coloca inmediatamente una nueva compra justo debajo del precio actual respetando el tope de $75,
          y desplaza suavemente grid_min y grid_max hacia arriba manteniendo exactamente max_active_buys.
        - Trailing Down Seguro: Si el precio cae al suelo del grid y hay USDT libre, añade
          un escalón inferior respetando el suelo del 10% y manteniendo intactas las ventas.
        """
        if not getattr(self, 'trailing_grid', True) or not self.levels:
            return False

        decimals = 5 if current_price < 1.0 else (2 if current_price > 50 else 4)
        spacing_mult = 1.0 + (float(self.spacing) / 100.0)
        target_buys = max(4, min(12, int(self.capital // max(1.0, self.max_order_usdt))))
        max_active_buys = getattr(self, 'max_active_buys', target_buys)
        max_order_cap = getattr(self, 'max_order_usdt', 75.0)

        # 1. Ventana Deslizante Trailing Up: Adaptar las compras al avance alcista del precio
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            buy_orders = sorted([o for o in open_orders if o.get('side') == 'buy'], key=lambda x: float(x.get('price', 0)), reverse=True)
            
            if buy_orders:
                highest_buy_p = float(buy_orders[0].get('price', 0))
                candidate_buy_p = round(highest_buy_p * spacing_mult, decimals)
                # Salvaguarda: No recomprar en un nivel que ya fue comprado y espera venta (+spacing)
                p_buys = [float(b['price']) for b in self.get_pending_buy_inventory() if b.get('remaining', 0) > 0.01]
                ex_sells = [float(o['price']) for o in open_orders if o.get('side') == 'sell']
                if any(abs(candidate_buy_p - pb) / candidate_buy_p < 0.003 for pb in p_buys) or any(abs(candidate_buy_p - ps) / candidate_buy_p < 0.003 for ps in ex_sells):
                    return False

                # Si el precio actual supera la compra más alta en más del spacing (con microfiltro de 0.2%)
                if current_price >= round(candidate_buy_p * 1.002, decimals):
                    deepest_order = buy_orders[-1]
                    deepest_p = float(deepest_order.get('price', 0))
                    print(f"🚀 [TRAILING UP ADAPTATIVO] Precio ${current_price} despegado de ${highest_buy_p}. Cancelando compra más lejana ${deepest_p}...")
                    
                    try:
                        self.exchange.cancel_order(deepest_order['id'], self.symbol)
                        time.sleep(0.4)
                        buy_orders = buy_orders[:-1]
                    except Exception as e_c:
                        print(f"Aviso cancelando orden inferior: {e_c}")

                    # Consultar balance disponible y colocar la nueva compra superior pegada al mercado
                    try:
                        base_curr, quote_curr = self.get_base_quote()
                        bal = self.exchange.fetch_balance()
                        free_quote = float(bal.get('free', {}).get(quote_curr, 0))
                        reserve = getattr(self, 'reserve_usdt', 0.0)
                        usable = max(0.0, free_quote - reserve)
                        min_order_cost = max(15.0, max_order_cap * 0.4)
                        cost_to_use = min(usable, max_order_cap)
                        if cost_to_use >= min_order_cost and candidate_buy_p < current_price:
                            amt = round((cost_to_use / candidate_buy_p) * 0.998, 4)
                            new_buy = self.exchange.create_limit_buy_order(self.symbol, amt, candidate_buy_p)
                            print(f"✅ [TRAILING UP] Nueva compra pegada al mercado: {amt} {base_curr} @ ${candidate_buy_p} (${amt * candidate_buy_p:.2f} USDT) [ID: {new_buy['id']}]")
                            send_telegram(f"🚀 <b>TRAILING UP ADAPTATIVO</b> en {self.symbol}\nCancelada compra lejana en ${deepest_p}\nNueva compra pegada al precio: {amt} @ ${candidate_buy_p} (Precio: ${current_price})")
                    except Exception as e_b:
                        print(f"Error colocando nueva compra de trailing up: {e_b}")

                    # Desplazar límites de rejilla hacia arriba
                    delta = candidate_buy_p - highest_buy_p
                    self.grid_min = round(self.grid_min + delta, decimals)
                    self.grid_max = round(self.grid_max + delta, decimals)
                    self.stop_loss_price = round(self.grid_min * 0.95, decimals)
                    
                    # Actualizar niveles y persistencia
                    cfg_file = os.path.join(LOG_DIR, 'grid_config.json')
                    if os.path.exists(cfg_file):
                        try:
                            with open(cfg_file, 'r') as f: c_data = json.load(f)
                            c_data.update({'grid_min': self.grid_min, 'grid_max': self.grid_max, 'stop_loss_price': self.stop_loss_price, 'updated_at': datetime.now().isoformat()})
                            with open(cfg_file, 'w') as f: json.dump(c_data, f, indent=2)
                        except Exception: pass
                    
                    self.sync_open_orders_file(self.exchange.fetch_open_orders(self.symbol))
                    return True
        except Exception as e_sw:
            print(f"Aviso en ventana deslizante: {e_sw}")

        # 2. Trailing Down Seguro: precio en el suelo y existe liquidez para comprar
        if getattr(self, 'trailing_down', True):
            down_trigger = self.grid_min * 1.005
            if current_price <= down_trigger:
                base_floor = getattr(self, 'trailing_down_floor', round(self.grid_min * 0.90, decimals))
                candidate_min = round(self.grid_min / spacing_mult, decimals)

                if candidate_min >= base_floor:
                    try:
                        _, quote_curr = self.get_base_quote()
                        bal = self.exchange.fetch_balance()
                        free_quote = float(bal.get('free', {}).get(quote_curr, 0))
                        usable_quote = max(0.0, free_quote - getattr(self, 'reserve_usdt', 0.0))
                    except Exception:
                        usable_quote = 0.0

                    min_order_cost = max(15.0, getattr(self, 'max_order_usdt', 50.0) * 0.4)
                    if usable_quote >= min_order_cost:
                        old_min = self.grid_min
                        self.grid_min = candidate_min
                        self.levels.insert(0, {'level': -1, 'price': candidate_min, 'type': 'buy', 'filled': False, 'order_id': None})
                        for i, lvl in enumerate(self.levels): lvl['level'] = i
                        self.num_levels = len(self.levels)
                        print(f"\n📉 [TRAILING DOWN] Suelo expandido (+{self.spacing}%): ${old_min} -> ${candidate_min}")
                        try:
                            cfg_file = os.path.join(LOG_DIR, 'grid_config.json')
                            if os.path.exists(cfg_file):
                                with open(cfg_file, 'r') as f: c_data = json.load(f)
                                c_data.update({'grid_min': self.grid_min, 'trailing_down_floor': base_floor, 'levels': self.levels, 'num_levels': self.num_levels, 'updated_at': datetime.now().isoformat()})
                                with open(cfg_file, 'w') as f: json.dump(c_data, f, indent=2)
                        except Exception: pass
                        self.reconcile_quote_inventory(current_price)
                        send_telegram(f"📉 <b>TRAILING DOWN</b> en {self.symbol} (${current_price}): Añadido escalón ${candidate_min} (Margen: +{self.spacing}%). Ventas previas 100% preservadas.")
                        return True
        return False

    def check_stop_loss(self, current_price, grid_min):
        """
        Función: check_stop_loss
        Supervisa si el precio vulnera el límite de pérdida configurado ('hold' o 'market_sell').
        """
        stop_loss = float(self.stop_loss_price) if self.stop_loss_price else (grid_min * STOP_LOSS_MULTIPLE)
        if current_price <= stop_loss:
            print(f"⚠️ STOP-LOSS ACTIVADO en {self.symbol}: ${current_price} <= ${stop_loss} [Modo: {self.stop_loss_mode.upper()}]")
            if self.stop_loss_mode == 'market_sell':
                send_telegram(f"🚨 STOP-LOSS AUTOMÁTICO ACTIVADO en {self.symbol}: Precio ${current_price} <= ${stop_loss}. Liquidando a mercado...")
                try:
                    self.cancel_old_orders()
                    time.sleep(1.0)
                    base_curr, _ = self.get_base_quote()
                    balance = self.exchange.fetch_balance()
                    sell_amount = round(float(balance.get('free', {}).get(base_curr, 0)) * 0.998, 4)
                    if (sell_amount * current_price) >= 1.0:
                        order = self.exchange.create_market_sell_order(self.symbol, sell_amount)
                        print(f"   -> Liquidación a mercado ejecutada: {sell_amount} {base_curr} [ID: {order['id']}]")
                        send_telegram(f"✅ Liquidación completada: {sell_amount} {base_curr} vendidos a mercado. Bot pausado.")
                    self.sync_open_orders_file(self.exchange.fetch_open_orders(self.symbol))
                    self.running = False
                    return True
                except Exception as e:
                    print(f"Error crítico en Stop-Loss: {e}")
                    send_telegram(f"❌ Error al ejecutar venta de Stop-Loss: {e}")
                    return True
            else:
                send_telegram(f"⚠️ AVISO: Precio ${current_price} en Stop-Loss (${stop_loss}). Modo 'Hold & Rebound' activo.")
                return False

        return False

    def check_take_profit(self):
        """
        Función: check_take_profit
        Evalúa el cumplimiento del objetivo global de beneficio sin repetir alertas en bucle continuo.
        """
        status = self.get_portfolio_status()
        target_pct = TAKE_PROFIT_PCT * 100
        if status and status['pnl_pct'] >= target_pct:
            if not self.take_profit_notified:
                print(f"🎯 TAKE-PROFIT ALCANZADO en {self.symbol}: {status['pnl_pct']:.1f}%")
                self.take_profit_notified = True
                return True
        elif status and status['pnl_pct'] < target_pct:
            self.take_profit_notified = False
        return False

    def get_portfolio_status(self):
        """
        Función: get_portfolio_status
        Calcula el estado consolidado de la cuenta en USDT y la moneda base.
        """
        try:
            base_curr, quote_curr = self.get_base_quote()
            b = self.exchange.fetch_balance()
            qv, qf, qu = float(b.get('total', {}).get(quote_curr, 0)), float(b.get('free', {}).get(quote_curr, 0)), float(b.get('used', {}).get(quote_curr, 0))
            bv, bf, bu = float(b.get('total', {}).get(base_curr, 0)), float(b.get('free', {}).get(base_curr, 0)), float(b.get('used', {}).get(base_curr, 0))
            current_price = float(self.exchange.fetch_ticker(self.symbol)['last'])
            total_usdt = qv + (bv * current_price)
            cap = float(self.capital) if hasattr(self, 'capital') and self.capital > 0 else CAPITAL
            p_buys = self.get_pending_buy_inventory()
            cost_inv = sum(float(b.get('price', 0)) * float(b.get('remaining', 0)) for b in p_buys)
            if bv >= 1.0 and cost_inv > 0:
                u_pnl = (bv * current_price) - cost_inv
                p_pct = (u_pnl / cost_inv) * 100
            else:
                u_pnl = 0.0
                p_pct = 0.0
            return {
                'symbol': self.symbol, 'current_price': current_price, 'total_balance': total_usdt,
                'quote_balance': qv, 'quote_free': qf, 'quote_used': qu,
                'base_balance': bv, 'base_free': bf, 'base_used': bu,
                'capital_baseline': cap, 'unrealized_pnl': round(u_pnl, 4), 'pnl_pct': round(p_pct, 4),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            print(f"Error obteniendo estado de portafolio: {e}")
            return None

    def run_once(self):
        """
        Función: run_once
        Ejecuta un ciclo completo de inspección de mercado, rebalanceo y supervisión de órdenes.
        """
        print(f"\n--- CICLO BOT ({self.symbol}): {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---")
        self.load_config()

        try:
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
        except Exception as e:
            print(f"Error consultando precio de {self.symbol}: {e}")
            return

        now = datetime.now()
        open_orders = self.exchange.fetch_open_orders(self.symbol)
        self.sync_open_orders_file(open_orders)

        needs_rebalance = False
        if not self.levels or not open_orders or getattr(self, 'force_rebalance', False):
            needs_rebalance = True
        elif self.last_rebalance:
            last_reb = datetime.fromisoformat(self.last_rebalance)
            if (now - last_reb).total_seconds() >= REBALANCE_INTERVAL:
                needs_rebalance = True

        if needs_rebalance:
            is_manual_force = getattr(self, 'force_rebalance', False)
            if is_manual_force or not open_orders:
                print(f"Ejecutando rebalanceo forzado total de {self.symbol}...")
                self.cancel_old_orders()
            else:
                print(f"Ejecutando rebalanceo periódico de liquidez (solo compras) en {self.symbol}...")
                self.cancel_old_orders(side='buy')
            time.sleep(1.0)
            self.setup_grid({'grid_min': self.grid_min, 'grid_max': self.grid_max, 'spacing': self.spacing, 'grid_levels': getattr(self, 'num_levels', NUM_LEVELS)})
            self.place_grid_orders()
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            self.sync_open_orders_file(open_orders)
            self.force_rebalance = False
            try:
                cfg_f = os.path.join(LOG_DIR, 'grid_config.json')
                if os.path.exists(cfg_f):
                    with open(cfg_f, 'r') as f: c_data = json.load(f)
                    c_data['force_rebalance'] = False
                    with open(cfg_f, 'w') as f: json.dump(c_data, f, indent=2)
            except Exception: pass

        self.monitor_and_cycle()
        self.reconcile_orphan_inventory(current_price)
        self.reconcile_quote_inventory(current_price)
        self.check_trailing_grid(current_price)

        if self.check_stop_loss(current_price, self.grid_min):
            send_telegram(f"STOP-LOSS ALCANZADO en {self.symbol}: ${current_price}")
        if self.check_take_profit():
            send_telegram(f"TAKE-PROFIT ALCANZADO en {self.symbol}")

        status = self.get_portfolio_status()
        if status:
            try:
                with open(METRICS_FILE, 'w') as f: json.dump({'timestamp': datetime.now().isoformat(), 'symbol': self.symbol, 'portfolio': status}, f, indent=2)
            except Exception as e: print(f"Error guardando metrics: {e}")

    def run(self):
        """
        Función: run
        Bucle permanente de ejecución con intervalos de escaneo regulares.
        """
        print(f"Iniciando Grid Bot continuo ({self.symbol})...")
        self.running = True
        try:
            while self.running:
                self.run_once()
                time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:
            print("\nDeteniendo Grid Bot ordenadamente...")
            self.running = False
        except Exception as e:
            print(f"Excepción no controlada en bucle principal: {e}")
            time.sleep(10)

if __name__ == '__main__':
    bot = GridBot()
    bot.run()
