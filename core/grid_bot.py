"""
==============================================================================
GRID BOT PROFESIONAL MULTI-PAR - KUCOIN
Soporte dinámico para cualquier par spot (KAS/USDT, BTC/USDT, ETH/USDT, SOL/USDT).
Reconciliación automática de inventario, respeto de mínimos y control desde ERP.
==============================================================================
"""

import ccxt
import json
import time
import sys
import os
from datetime import datetime
try:
    from market_analyzer import analyze_market, save_analysis
except ImportError:
    analyze_market = None
    save_analysis = None
from config import (
    KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE,
    SYMBOL, CAPITAL, GRID_SPACING_PCT, NUM_LEVELS, FEE_RATE,
    LOG_DIR, TRADE_LOG, METRICS_FILE, STATUS_FILE, OPEN_ORDERS_FILE,
    SCAN_INTERVAL, REBALANCE_INTERVAL, STOP_LOSS_MULTIPLE,
    TAKE_PROFIT_PCT, MAX_DAILY_LOSS
)
from ai_memory_db import set_persistent_param, get_persistent_param

def acquire_single_instance_lock(lock_path='/tmp/grid_bot.lock'):
    """
    Función: acquire_single_instance_lock
    Garantiza la ejecución exclusiva de una única instancia del Grid Bot
    mediante bloqueo de archivo a nivel de kernel (fcntl.flock). Evita
    duplicación de órdenes por procesos en paralelo.
    """
    try:
        import fcntl
        lock_file = open(lock_path, 'w')
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except (IOError, BlockingIOError):
        print(f"[SEGURIDAD] Ya existe otra instancia del Grid Bot ejecutándose con el bloqueo {lock_path}. Abortando.")
        sys.exit(0)
    except Exception as e:
        print(f"[AVISO] No se pudo verificar bloqueo exclusivo ({e}). Continuando con precaución.")
        return None

def send_telegram(message):
    """
    Función: send_telegram
    Envía notificaciones críticas del bot hacia la IA Pichita.
    """
    try:
        import subprocess
        if "STOP-LOSS" in message or "TAKE-PROFIT" in message or "CRITICO" in message.upper():
            subprocess.Popen(
                ["python3", "/home/user/.hermes/ia_crypto_reporter.py", "--tipo", "alerta", "--alerta", message],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
            )
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
        self.running = False
        self.symbol = SYMBOL
        self.grid_min = 0.033
        self.grid_max = 0.041
        self.spacing = GRID_SPACING_PCT
        self.levels = []
        self.trades = []
        self.known_trade_ids = set()
        self.last_rebalance = None
        self.stop_loss_mode = 'hold'
        self.stop_loss_price = None
        self.capital = float(CAPITAL)
        self.trailing_grid = True
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
        Carga el historial de ejecuciones previas y registra sus identificadores.
        """
        if os.path.exists(TRADE_LOG):
            try:
                with open(TRADE_LOG, 'r') as f:
                    self.trades = json.load(f)
                self.known_trade_ids = {t.get('id') for t in self.trades if t.get('id')}
            except Exception as e:
                print(f"Error cargando trades: {e}")
                self.trades = []
                self.known_trade_ids = set()

    def get_pending_buy_inventory(self):
        """
        Función: get_pending_buy_inventory
        Calcula los lotes de compra reales pendientes de vender.
        Garantiza que el total de la moneda base en inventario coincida estrictamente
        con el saldo físico real disponible en el exchange (asignación 1:1 por lote íntegro, sin dilución ni órdenes fantasma).
        """
        try:
            self.load_trades()
            base_curr, quote_curr = self.get_base_quote()
            bal = self.exchange.fetch_balance()
            total_base = float(bal.get('total', {}).get(base_curr, 0))
            if total_base <= 0.5:
                return []

            # Recorrer compras recientes desde la más nueva hacia atrás para emparejar con el saldo físico
            recent_buys = []
            for t in reversed(self.trades):
                if t.get('symbol') != self.symbol or t.get('side') != 'buy':
                    continue
                recent_buys.append({
                    'id': t.get('id'),
                    'price': float(t.get('price', 0)),
                    'remaining': float(t.get('amount', 0)),
                    'amount': float(t.get('amount', 0)),
                    'timestamp': t.get('timestamp')
                })

            # Agrupar compras al mismo nivel de precio (ej. parciales consecutivos)
            allocated = 0.0
            matched_inventory = []

            for b in recent_buys:
                if allocated >= total_base - 0.5:
                    break
                needed = total_base - allocated
                take = min(b['remaining'], needed)
                if take > 0.1:
                    existing = next((inv for inv in matched_inventory if abs(inv['price'] - b['price']) / b['price'] < 0.0005), None)
                    if existing:
                        existing['remaining'] += take
                        existing['amount'] += take
                    else:
                        matched_inventory.append({
                            'id': b['id'],
                            'price': b['price'],
                            'remaining': take,
                            'amount': take,
                            'timestamp': b['timestamp']
                        })
                    allocated += take

            return matched_inventory
        except Exception as e:
            print(f"Error calculando inventario de compras: {e}")
            return []

    def load_config(self):
        """
        Función: load_config
        Carga la configuración activa del grid desde SQLite y grid_config.json preservando el capital real.
        """
        # 1. Recuperar capital prioritariamente desde base de datos SQLite indestructible
        try:
            db_cap = get_persistent_param('capital')
            if db_cap is not None and float(db_cap) > 0:
                self.capital = float(db_cap)
        except Exception:
            pass

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

                # Si ya se cargó de SQLite, mantenerlo; sino, de JSON; último recurso CAPITAL
                saved_cap = config.get('capital')
                if self.capital and self.capital > 0:
                    pass
                elif saved_cap and float(saved_cap) > 0:
                    self.capital = float(saved_cap)
                else:
                    self.capital = float(CAPITAL)

                self.trailing_grid = bool(config.get('trailing_grid', True))
                self.force_rebalance = bool(config.get('force_rebalance', False))
                print(f"Configuración cargada: Par={self.symbol}, Spacing={self.spacing}%, Capital={self.capital} USDT, Trailing={self.trailing_grid}, SL_Modo={self.stop_loss_mode}, Rango=[{self.grid_min}, {self.grid_max}], ForceRebalance={self.force_rebalance}")
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
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            # Persistir indestructiblemente en SQLite
            try:
                if hasattr(self, 'capital') and self.capital and self.capital > 0:
                    set_persistent_param('capital', float(self.capital))
            except Exception:
                pass
        except Exception as e:
            print(f"Error guardando config: {e}")

    def save_trades(self):
        """
        Función: save_trades
        Guarda el historial de operaciones ordenado cronológicamente.
        """
        try:
            self.trades.sort(key=lambda x: x.get('timestamp', ''))
            with open(TRADE_LOG, 'w') as f:
                json.dump(self.trades, f, indent=2)
        except Exception as e:
            print(f"Error guardando trades: {e}")

    def sync_open_orders_file(self, open_orders):
        """
        Función: sync_open_orders_file
        Exporta las órdenes vivas en KuCoin para el consumo en tiempo real del ERP.
        """
        try:
            orders_data = []
            for o in open_orders:
                orders_data.append({
                    'id': o.get('id'),
                    'symbol': o.get('symbol', self.symbol),
                    'side': o.get('side'),
                    'price': float(o.get('price', 0)),
                    'amount': float(o.get('amount', 0)),
                    'cost': float(o.get('cost') or (float(o.get('price', 0)) * float(o.get('amount', 0)))),
                    'status': o.get('status', 'open'),
                    'timestamp': o.get('datetime')
                })
            with open(OPEN_ORDERS_FILE, 'w') as f:
                json.dump(orders_data, f, indent=2)
        except Exception as e:
            print(f"Error sincronizando open_orders.json: {e}")

    def cancel_old_orders(self, cancel_sells=False):
        """
        Función: cancel_old_orders
        Cancela las órdenes de compra (BUY) para recolocar la rejilla según el mercado.
        Protege las órdenes de venta (SELL) activas en el exchange (cancel_sells=False)
        para no resetear su turno ni perturbar sus ganancias en espera de ejecución.
        """
        try:
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            if open_orders:
                orders_to_cancel = [o for o in open_orders if cancel_sells or o.get('side') == 'buy']
                target_desc = "todas las" if cancel_sells else "de compra (BUY)"
                if orders_to_cancel:
                    print(f"Cancelando {len(orders_to_cancel)} órdenes {target_desc} en {self.symbol}...")
                    for order in orders_to_cancel:
                        try:
                            self.exchange.cancel_order(order['id'], self.symbol)
                            time.sleep(0.1)
                        except Exception as e:
                            print(f"Error cancelando orden {order['id']}: {e}")
                    return True
                else:
                    print(f"No hay órdenes de compra que cancelar en {self.symbol}. Las ventas permanecen intactas.")
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
        pending_buys = self.get_pending_buy_inventory()
        pending_buy_prices = [float(b['price']) for b in pending_buys if b.get('remaining', 0) > 0.01]

        # Filtrar niveles donde ya exista orden BUY abierta o posición en cartera pendiente de venta
        filtered_buy_levels = []
        for lvl in buy_levels:
            lp = lvl['price']
            has_buy = any(abs(lp - ep) / lp < 0.003 for ep in existing_buy_prices)
            has_hold = any(abs(lp - pp) / lp < 0.003 for pp in pending_buy_prices)
            if not has_buy and not has_hold:
                filtered_buy_levels.append(lvl)
            else:
                print(f"   [NIVEL BLOQUEADO] Compra en ${lp} omitida para evitar duplicados en el mismo precio.")

        min_cost = 1.05
        # Respetar estrictamente el tope de capital asignado configurado por el usuario en el modal
        max_capital_allowed = float(self.capital) if hasattr(self, 'capital') and self.capital > 0 else free_quote
        quote_to_allocate = min(free_quote, max_capital_allowed)

        print(f"Capital asignado configurado: ${max_capital_allowed:.2f} USDT | Saldo libre disponible: ${free_quote:.2f} USDT | Presupuesto efectivo: ${quote_to_allocate:.2f} USDT")

        if filtered_buy_levels and quote_to_allocate >= min_cost:
            max_buy_orders = max(1, int(quote_to_allocate // min_cost))
            effective_buy_levels = filtered_buy_levels[:max_buy_orders]
            quote_per_order = quote_to_allocate / len(effective_buy_levels)

            for lvl in effective_buy_levels:
                price = lvl['price']
                amount = round((quote_per_order / price) * 0.998, 4)
                cost = amount * price
                if cost >= 1.0:
                    try:
                        order = self.exchange.create_limit_buy_order(self.symbol, amount, price)
                        lvl['order_id'] = order['id']
                        placed += 1
                        print(f"   [BUY] Nivel {lvl['level']}: {amount} {base_curr} @ ${price}")
                    except Exception as e:
                        print(f"   [ERROR BUY] @ ${price}: {e}")
                        failed += 1

        # 2. Órdenes de VENTA (Protección estricta: cada venta vinculada a su compra real con margen garantizado >= spacing)
        pending_buys = self.get_pending_buy_inventory()
        spacing_mult = 1.0 + (self.spacing / 100.0)
        decimals = 5 if current_price < 1.0 else (2 if current_price > 50 else 4)
        open_orders_existing_sells = self.exchange.fetch_open_orders(self.symbol)
        existing_sell_prices = [float(o['price']) for o in open_orders_existing_sells if o.get('side') == 'sell']

        if pending_buys and free_base > 0:
            # Agrupar lotes que no alcancen el mínimo de 1.0 USDT
            orders_to_place = []
            accum_kas = 0.0

            for pb in pending_buys:
                kas_lot = pb['remaining']
                target_p = round(pb['price'] * spacing_mult, decimals)
                val = kas_lot * target_p
                if val < 1.0:
                    accum_kas += kas_lot
                else:
                    if accum_kas > 0:
                        kas_lot += accum_kas
                        accum_kas = 0.0
                    orders_to_place.append({'amount': kas_lot, 'price': target_p})

            if accum_kas > 0 and orders_to_place:
                orders_to_place[-1]['amount'] += accum_kas

            # Venta estricta 1:1 por lote completo: cada compra se vende íntegramente a su precio objetivo (+spacing)
            # Se ordena por precio ascendente para colocar primero las ventas más próximas al precio actual
            orders_to_place.sort(key=lambda o: o['price'])
            available_kas = free_base

            for o in orders_to_place:
                if available_kas <= 0.5:
                    break
                prc = o['price']
                # Si ya existe una orden de venta activa a este precio, no duplicar ni alterar
                if any(abs(prc - esp) / prc < 0.001 for esp in existing_sell_prices):
                    continue
                # Asignación de lote completo 1:1 deduciendo comisión real (0.2%) sin dilución ni ratio
                lot_qty = min(o['amount'], available_kas)
                amt = round(lot_qty * 0.998, 4)
                if amt * prc >= 1.0:
                    try:
                        order = self.exchange.create_limit_sell_order(self.symbol, amt, prc)
                        placed += 1
                        available_kas -= lot_qty
                        existing_sell_prices.append(prc)
                        print(f"   [SELL 1:1 ÍNTEGRO] {amt} {base_curr} @ ${prc} (Margen: +{self.spacing}%)")
                    except Exception as e:
                        print(f"   [ERROR SELL 1:1] @ ${prc}: {e}")
                        failed += 1
        elif free_base * current_price >= 1.0:
            # Saldo huérfano sin compra registrada previa: venta garantizada por encima del precio de mercado
            sell_price = round(current_price * spacing_mult, decimals)
            sell_amount = round(free_base * 0.998, 4)
            if sell_amount * sell_price >= 1.0 and not any(abs(sell_price - esp) / sell_price < 0.001 for esp in existing_sell_prices):
                try:
                    order = self.exchange.create_limit_sell_order(self.symbol, sell_amount, sell_price)
                    placed += 1
                    print(f"   [SELL HUÉRFANO] {sell_amount} {base_curr} @ ${sell_price}")
                except Exception as e:
                    print(f"   [ERROR SELL HUÉRFANO]: {e}")
                    failed += 1

        open_orders = self.exchange.fetch_open_orders(self.symbol)
        self.sync_open_orders_file(open_orders)
        print(f"Resumen Rejilla {self.symbol}: {placed} colocadas. Abiertas totales: {len(open_orders)}")
        return placed, failed

    def reconcile_orphan_inventory(self, current_price):
        """
        Función: reconcile_orphan_inventory
        Detecta si existe saldo libre de la moneda base sin orden de venta en KuCoin y coloca órdenes límite
        o agrupa el remanente en órdenes existentes si el precio de venta cumple estrictamente el spacing.
        """
        try:
            base_curr, quote_curr = self.get_base_quote()
            balance = self.exchange.fetch_balance()
            free_base = float(balance.get('free', {}).get(base_curr, 0))
            if free_base <= 0.5:
                return False

            spacing_mult = 1.0 + (self.spacing / 100.0)
            decimals = 5 if current_price < 1.0 else (2 if current_price > 50 else 4)

            pending_buys = self.get_pending_buy_inventory()
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            sell_orders = [o for o in open_orders if o['side'] == 'sell']

            placed_any = False
            remaining_free = free_base

            if pending_buys:
                for pb in pending_buys:
                    target_p = round(pb['price'] * spacing_mult, decimals)
                    existing_order = next((o for o in sell_orders if abs(float(o['price']) - target_p) / target_p < 0.001), None)
                    
                    lot_amount = round(min(pb['remaining'], remaining_free) * 0.998, 4)
                    if existing_order:
                        # Si ya existe orden y hay saldo libre huérfano asociado, agrupar
                        if lot_amount > 0.5:
                            new_amt = round(float(existing_order['amount']) + lot_amount, 4)
                            try:
                                self.exchange.cancel_order(existing_order['id'], self.symbol)
                                time.sleep(0.3)
                                order = self.exchange.create_limit_sell_order(self.symbol, new_amt, target_p)
                                print(f"   [RECONCILIACIÓN AGRUPADA] {new_amt} {base_curr} @ ${target_p} [ID: {order['id']}]")
                                remaining_free -= lot_amount
                                placed_any = True
                            except Exception as e:
                                print(f"   Aviso agrupando venta @ ${target_p}: {e}")
                    elif lot_amount * target_p >= 1.0:
                        try:
                            order = self.exchange.create_limit_sell_order(self.symbol, lot_amount, target_p)
                            print(f"   [RECONCILIACIÓN 1:1] Venta de {lot_amount} {base_curr} @ ${target_p} (Margen: +{self.spacing}%) [ID: {order['id']}]")
                            remaining_free -= lot_amount
                            placed_any = True
                        except Exception as e:
                            print(f"   Aviso colocando venta individual @ ${target_p}: {e}")

            # Si queda saldo menor a 1 USDT y hay órdenes de venta activas, agrupar en la venta más baja válida
            if remaining_free > 0.5 and remaining_free * current_price < 1.0 and sell_orders:
                lowest_sell = min(sell_orders, key=lambda o: float(o['price']))
                p = float(lowest_sell['price'])
                new_amt = round(float(lowest_sell['amount']) + remaining_free, 4)
                try:
                    self.exchange.cancel_order(lowest_sell['id'], self.symbol)
                    time.sleep(0.3)
                    order = self.exchange.create_limit_sell_order(self.symbol, new_amt, p)
                    print(f"   [AGRUPACIÓN DUST] Remanente {remaining_free:.4f} {base_curr} sumado a orden @ ${p} [Total: {new_amt}]")
                    placed_any = True
                except Exception as e:
                    print(f"   Aviso agrupando dust @ ${p}: {e}")

            if placed_any:
                open_orders = self.exchange.fetch_open_orders(self.symbol)
                self.sync_open_orders_file(open_orders)
                return True
        except Exception as e:
            print(f"Aviso en reconcile_orphan_inventory: {e}")
        return False

    def monitor_and_cycle(self):
        """
        Función: monitor_and_cycle
        Detección continua de ejecuciones mediante fetch_my_trades y colocación
        inmediata de la contra-orden correspondiente con ganancia mínima garantizada.
        """
        try:
            recent_trades = self.exchange.fetch_my_trades(self.symbol, limit=20)
            new_trades_detected = 0

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
                    new_trades_detected += 1
                    side = trade_record['side']
                    price = trade_record['price']
                    amount = trade_record['amount']
                    print(f"⚡ NUEVO TRADE EN KUCOIN ({self.symbol}): {side.upper()} {amount} @ ${price}")

                    # Disparo asíncrono a Telegram vía Hermes (Skill grid-trading-notifier)
                    try:
                        import subprocess
                        subprocess.Popen(
                            [
                                "python3", "./trade_notifier.py",
                                "--side", side,
                                "--price", str(price),
                                "--amount", str(amount),
                                "--symbol", self.symbol
                            ],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
                        )
                    except Exception as err_notif:
                        print(f"   -> Aviso disparando notificador Telegram: {err_notif}")

                    decimals = 5 if price < 1.0 else (2 if price > 50 else 4)
                    spacing_mult = 1.0 + (self.spacing / 100.0)

                    if side == 'buy':
                        # SALVAGUARDA DE GANANCIA: Venta estrictamente superior al precio de compra
                        min_gain_mult = max(1.0105, spacing_mult)
                        sell_price = round(price * min_gain_mult, decimals)
                        sell_amount = round(amount * 0.998, 4)
                        
                        # REGLA: Si ya existe orden de venta al mismo precio, agrupar para ahorrar comisiones y unificar parciales
                        open_orders_now = self.exchange.fetch_open_orders(self.symbol)
                        existing_sell = next((o for o in open_orders_now if o['side'] == 'sell' and abs(float(o['price']) - sell_price) / sell_price < 0.001), None)
                        
                        if existing_sell:
                            new_total_amt = round(float(existing_sell['amount']) + sell_amount, 4)
                            try:
                                self.exchange.cancel_order(existing_sell['id'], self.symbol)
                                time.sleep(0.3)
                                new_order = self.exchange.create_limit_sell_order(self.symbol, new_total_amt, sell_price)
                                print(f"   -> [VENTA AGRUPADA] Orden de venta unificada: {new_total_amt} @ ${sell_price} [ID: {new_order['id']}]")
                            except Exception as e:
                                print(f"   -> Error agrupando contra-orden SELL en ${sell_price}: {e}")
                        else:
                            cost = sell_amount * sell_price
                            if cost >= 1.0:
                                try:
                                    new_order = self.exchange.create_limit_sell_order(self.symbol, sell_amount, sell_price)
                                    print(f"   -> Contra-orden SELL colocada: {sell_amount} @ ${sell_price} [ID: {new_order['id']}]")
                                except Exception as e:
                                    print(f"   -> Error colocando contra-orden SELL: {e}")
                            else:
                                print(f"   -> Parcial ({sell_amount} KAS = ${cost:.3f} USDT) conservado en balance libre para agrupar en siguiente fill.")
                    elif side == 'sell':
                        buy_price = round(price / spacing_mult, decimals)
                        open_orders_now = self.exchange.fetch_open_orders(self.symbol)
                        existing_buys = [float(o['price']) for o in open_orders_now if o['side'] == 'buy']
                        if any(abs(buy_price - ep) / buy_price < 0.003 for ep in existing_buys):
                            print(f"   -> [OMITIDO] Ya existe orden BUY activa en nivel ${buy_price}")
                        else:
                            buy_amount = round(amount, 4)
                            cost = buy_amount * buy_price
                            if cost >= 1.0:
                                try:
                                    new_order = self.exchange.create_limit_buy_order(self.symbol, buy_amount, buy_price)
                                    print(f"   -> Contra-orden BUY colocada: {buy_amount} @ ${buy_price} [ID: {new_order['id']}]")
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
        Rejilla Dinámica Adaptativa (Trailing Up):
        Cuando el precio de mercado supera el 95% del límite superior de la rejilla,
        desplaza suavemente el rango completo hacia arriba para no quedar fuera de mercado,
        manteniendo el número de niveles y respetando estrictamente el capital asignado.
        """
        if not getattr(self, 'trailing_grid', True) or not self.levels:
            return False

        # Umbral de activación: precio alcanza o supera el 96% del límite superior
        trigger_price = self.grid_max * 0.96
        if current_price >= trigger_price:
            decimals = 5 if current_price < 1.0 else (2 if current_price > 50 else 4)
            step_pct = (self.spacing / 100.0)
            
            # Desplazar el rango hacia arriba según el spacing
            delta = round(current_price * step_pct, decimals)
            new_grid_min = round(self.grid_min + delta, decimals)
            new_grid_max = round(self.grid_max + delta, decimals)
            new_stop_loss = round(new_grid_min * 0.95, decimals)

            print(f"\n🚀 [TRAILING GRID ACTIVADO] Precio ${current_price} alcanzó zona alta (${trigger_price}).")
            print(f"   -> Desplazando rejilla: Min ${self.grid_min} -> ${new_grid_min} | Max ${self.grid_max} -> ${new_grid_max}")

            self.grid_min = new_grid_min
            self.grid_max = new_grid_max
            self.stop_loss_price = new_stop_loss
            self.force_rebalance = True

            # Persistir nueva configuración adaptativa
            try:
                cfg_file = os.path.join(LOG_DIR, 'grid_config.json')
                if os.path.exists(cfg_file):
                    with open(cfg_file, 'r') as f:
                        c_data = json.load(f)
                    c_data['grid_min'] = new_grid_min
                    c_data['grid_max'] = new_grid_max
                    c_data['stop_loss_price'] = new_stop_loss
                    c_data['force_rebalance'] = True
                    c_data['levels'] = []
                    c_data['updated_at'] = datetime.now().isoformat()
                    with open(cfg_file, 'w') as f:
                        json.dump(c_data, f, indent=2)
            except Exception as e:
                print(f"Aviso guardando trailing config: {e}")

            send_telegram(
                f"🚀 <b>TRAILING GRID ADAPTATIVO</b>\n"
                f"El precio de {self.symbol} (${current_price}) superó el umbral superior.\n"
                f"📈 <b>Nuevo Rango Adaptado:</b> ${new_grid_min} - ${new_grid_max}\n"
                f"🛡️ <b>Nuevo Stop-Loss:</b> ${new_stop_loss}\n"
                f"La cuadrícula continuará capturando beneficios sin salirse de rango."
            )
            return True
        return False

    def check_stop_loss(self, current_price, grid_min):
        """
        Función: check_stop_loss
        Supervisa si el precio de mercado vulnera el límite de pérdida configurado.
        Según el modo seleccionado ('hold' o 'market_sell'), ejecuta la liquidación a mercado
        o mantiene las posiciones emitiendo alertas de supervisión.
        """
        if self.stop_loss_price:
            stop_loss = float(self.stop_loss_price)
        else:
            stop_loss = grid_min * STOP_LOSS_MULTIPLE

        if current_price <= stop_loss:
            print(f"⚠️ STOP-LOSS ACTIVADO en {self.symbol}: ${current_price} <= ${stop_loss} [Modo: {self.stop_loss_mode.upper()}]")
            
            if self.stop_loss_mode == 'market_sell':
                print(f"⚡ Ejecutando Stop-Loss Automático a Mercado en {self.symbol}...")
                send_telegram(f"🚨 STOP-LOSS AUTOMÁTICO ACTIVADO en {self.symbol}: Precio ${current_price} <= ${stop_loss}. Cancelando órdenes y vendiendo a mercado...")
                try:
                    # 1. Cancelar todas las órdenes abiertas para liberar inventario bloqueado
                    self.cancel_old_orders()
                    time.sleep(1.0)
                    
                    # 2. Consultar balance libre de la moneda base
                    base_curr, quote_curr = self.get_base_quote()
                    balance = self.exchange.fetch_balance()
                    free_base = float(balance.get('free', {}).get(base_curr, 0))
                    sell_amount = round(free_base * 0.998, 4)
                    
                    # 3. Ejecutar venta a mercado de seguridad
                    if (sell_amount * current_price) >= 1.0:
                        order = self.exchange.create_market_sell_order(self.symbol, sell_amount)
                        print(f"   -> Liquidación a mercado ejecutada: {sell_amount} {base_curr} [ID: {order['id']}]")
                        send_telegram(f"✅ Liquidación de emergencia completada: {sell_amount} {base_curr} vendidos a mercado. Bot pausado por seguridad.")
                    else:
                        print(f"   -> Saldo libre insuficiente para orden mínima ({sell_amount} {base_curr})")
                    
                    # 4. Sincronizar open_orders y pausar el bot
                    open_orders = self.exchange.fetch_open_orders(self.symbol)
                    self.sync_open_orders_file(open_orders)
                    self.running = False
                    return True
                except Exception as e:
                    print(f"Error crítico en ejecución de Stop-Loss a mercado: {e}")
                    send_telegram(f"❌ Error al ejecutar venta de Stop-Loss en KuCoin: {e}")
                    return True
            else:
                # Modo 'hold': solo notificar sin vender a pérdida
                send_telegram(f"⚠️ AVISO DE MERCADO: Precio ${current_price} en zona de Stop-Loss (${stop_loss}). Manteniendo inventario según modo 'Hold & Rebound'.")
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
            balance = self.exchange.fetch_balance()
            quote_val = float(balance.get('total', {}).get(quote_curr, 0))
            base_val = float(balance.get('total', {}).get(base_curr, 0))
            ticker = self.exchange.fetch_ticker(self.symbol)
            current_price = float(ticker['last'])
            total_usdt = quote_val + (base_val * current_price)
            pnl_pct = ((total_usdt - CAPITAL) / CAPITAL) * 100 if CAPITAL > 0 else 0

            return {
                'symbol': self.symbol,
                'quote_balance': quote_val,
                'base_balance': base_val,
                'current_price': current_price,
                'total_balance': total_usdt,
                'pnl_pct': pnl_pct,
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
            print(f"Ejecutando rebalanceo solicitado de {self.symbol}...")
            self.cancel_old_orders()
            time.sleep(1.0)
            analysis_data = {
                'grid_min': self.grid_min,
                'grid_max': self.grid_max,
                'spacing': self.spacing,
                'grid_levels': getattr(self, 'num_levels', NUM_LEVELS)
            }
            self.setup_grid(analysis_data)
            self.place_grid_orders()
            open_orders = self.exchange.fetch_open_orders(self.symbol)
            self.sync_open_orders_file(open_orders)
            self.force_rebalance = False
            try:
                cfg_file = os.path.join(LOG_DIR, 'grid_config.json')
                if os.path.exists(cfg_file):
                    with open(cfg_file, 'r') as f:
                        c_data = json.load(f)
                    c_data['force_rebalance'] = False
                    with open(cfg_file, 'w') as f:
                        json.dump(c_data, f, indent=2)
            except Exception:
                pass

        self.reconcile_orphan_inventory(current_price)
        self.check_trailing_grid(current_price)
        self.monitor_and_cycle()

        if self.check_stop_loss(current_price, self.grid_min):
            send_telegram(f"STOP-LOSS ALCANZADO en {self.symbol}: ${current_price}")
        if self.check_take_profit():
            send_telegram(f"TAKE-PROFIT ALCANZADO en {self.symbol}")

        status = self.get_portfolio_status()
        if status:
            metrics = {
                'timestamp': datetime.now().isoformat(),
                'symbol': self.symbol,
                'portfolio': status,
            }
            try:
                with open(METRICS_FILE, 'w') as f:
                    json.dump(metrics, f, indent=2)
            except Exception as e:
                print(f"Error guardando metrics: {e}")

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
    _lock = acquire_single_instance_lock()
    bot = GridBot()
    bot.run()
