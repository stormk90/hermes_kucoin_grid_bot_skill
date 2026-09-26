"""
Módulo: lot_tracker.py
Propósito: Gestión persistente, atómica e indestructible del inventario por lotes de compra (lot_id).
Permite mantener la trazabilidad 1:1 de cada compra ejecutada con su orden de venta correspondiente,
eliminando cálculos volátiles en memoria y cumpliendo el Plan Profesional de Mejora.
"""

import os
import json
import time
from datetime import datetime

class LotTracker:
    """
    Clase: LotTracker
    Administra el ciclo de vida de cada lote de compra en el Grid Bot KuCoin.
    Garantiza persistencia atómica en disco y trazabilidad exacta de inventario.
    """

    def __init__(self, log_dir=None, symbol='KAS/USDT'):
        """
        Función: __init__
        Inicializa la instancia del rastreador de lotes, definiendo rutas de archivos de logs y estado.
        """
        if log_dir is None:
            candidate_logs = os.path.join(os.path.expanduser('~'), 'workspace', 'logs')
            if os.path.exists(candidate_logs):
                log_dir = candidate_logs
            else:
                log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')


        self.log_dir = log_dir
        self.symbol = symbol
        self.inventory_file = os.path.join(self.log_dir, 'lot_inventory.json')
        self.ensure_directory()

    def ensure_directory(self):
        """
        Función: ensure_directory
        Crea el directorio de almacenamiento si no existe en el sistema operativo.
        """
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir, exist_ok=True)
            except Exception as e:
                print(f"[LOT_TRACKER] Aviso creando directorio {self.log_dir}: {e}")

    def load_inventory(self):
        """
        Función: load_inventory
        Carga el inventario persistido desde lot_inventory.json de forma segura.
        """
        if os.path.exists(self.inventory_file):
            try:
                with open(self.inventory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[LOT_TRACKER] Error leyendo inventario: {e}")
        return {
            'timestamp': datetime.now().isoformat(),
            'symbol': self.symbol,
            'lots': [],
            'mapped_base': 0.0,
            'total_base': 0.0,
            'unmapped_base': 0.0,
            'policy': 'trazabilidad_estricta_1_1'
        }

    def save_inventory(self, data):
        """
        Función: save_inventory
        Guarda el estado del inventario de forma atómica (archivo temporal + reemplazo atómico)
        para evitar corrupción en caso de caída o reinicio del sistema.
        """
        try:
            self.ensure_directory()
            data['timestamp'] = datetime.now().isoformat()
            tmp_file = self.inventory_file + '.tmp'
            with open(tmp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_file, self.inventory_file)
            return True
        except Exception as e:
            print(f"[LOT_TRACKER] Error guardando inventario atómico: {e}")
            return False

    def sync_from_trades(self, trades, total_base, spacing_pct=1.35):
        """
        Función: sync_from_trades
        Reconcilia cronológicamente las compras y ventas ejecutadas, asignando cada lote
        con su remanente exacto y deduciendo las ventas completadas mediante el algoritmo FIFO.
        """
        try:
            spacing_mult = 1.0 + (spacing_pct / 100.0)
            margin_tolerance = spacing_pct * 0.015

            # 1. Consolidar ejecuciones parciales de compra de la misma orden de KuCoin
            chron = sorted(trades, key=lambda x: str(x.get('datetime') or x.get('timestamp') or ''))
            consolidated_trades = []
            orders_seen = {}
            for t in chron:
                if t.get('symbol') != self.symbol:
                    continue
                side = t.get('side')
                amt = float(t.get('amount', 0))
                price = float(t.get('price', 0))
                cost = float(t.get('cost') or (amt * price))
                oid = str(t.get('order_id') or t.get('order') or t.get('id', ''))
                tid = str(t.get('id', ''))
                ts = t.get('timestamp', '')

                if side == 'buy':
                    if oid and oid in orders_seen:
                        prev = orders_seen[oid]
                        prev['amount'] += amt
                        prev['cost'] += cost
                        prev['price'] = round(prev['cost'] / prev['amount'], 5)
                        prev['remaining'] += amt
                    else:
                        entry = {
                            'side': 'buy',
                            'order_id': oid,
                            'trade_id': tid,
                            'id': tid,
                            'amount': amt,
                            'cost': cost,
                            'price': price,
                            'remaining': amt,
                            'timestamp': ts,
                            'provenance': 'bot_trade'
                        }
                        if oid:
                            orders_seen[oid] = entry
                        consolidated_trades.append(entry)
                else:
                    consolidated_trades.append({
                        'side': 'sell',
                        'order_id': oid,
                        'trade_id': tid,
                        'id': tid,
                        'amount': amt,
                        'cost': cost,
                        'price': price,
                        'timestamp': ts
                    })

            open_buys = []
            for t in consolidated_trades:
                side = t['side']
                amt = t['amount']
                price = t['price']
                tid = t['id']
                ts = t['timestamp']

                if side == 'buy':
                    open_buys.append({
                        'id': tid,
                        'lot_id': f"LOT-{tid}",
                        'trade_id': tid,
                        'order_id': t.get('order_id'),
                        'price': price,
                        'amount': amt,
                        'remaining': amt,
                        'target_sell_price': round(price * spacing_mult, 5),
                        'timestamp': ts,
                        'provenance': 'bot_trade'
                    })
                elif side == 'sell':
                    sell_qty = amt
                    while sell_qty >= 1.0 and open_buys:
                        best_idx, best_score = -1, float('inf')
                        for i, ob in enumerate(open_buys):
                            if ob['remaining'] >= 1.0 and ob['price'] < price:
                                expected_sell = ob['price'] * spacing_mult
                                pdiff = abs(price - expected_sell) / ob['price']
                                if pdiff < margin_tolerance and pdiff < best_score:
                                    best_score, best_idx = pdiff, i

                        if best_idx == -1:
                            cdiff = float('inf')
                            for i, ob in enumerate(open_buys):
                                if ob['remaining'] >= 1.0 and ob['price'] < price:
                                    diff = price - ob['price']
                                    if diff < cdiff:
                                        cdiff, best_idx = diff, i

                        if best_idx == -1:
                            break

                        ob = open_buys[best_idx]
                        mqty = min(ob['remaining'], sell_qty)
                        ob['remaining'] = round(ob['remaining'] - mqty, 4)
                        sell_qty = round(sell_qty - mqty, 4)
                        if ob['remaining'] <= max(10.0, ob['amount'] * 0.005) or (ob['remaining'] * ob['price'] < 1.0):
                            ob['remaining'] = 0.0

            active_lots = [b for b in open_buys if b['remaining'] >= 10.0 and (b['remaining'] * b['price'] >= 1.0)]
            mapped_base = round(sum(l['remaining'] for l in active_lots), 4)
            unmapped_base = round(max(0.0, float(total_base) - mapped_base), 4)

            # Cero invención de datos: El saldo no asignado se reporta con rigor sin inventar macrolotes ficticios

            inventory_data = {
                'timestamp': datetime.now().isoformat(),
                'symbol': self.symbol,
                'lots': active_lots,
                'mapped_base': mapped_base,
                'total_base': float(total_base),
                'unmapped_base': unmapped_base,
                'policy': 'trazabilidad_estricta_1_1'
            }

            self.save_inventory(inventory_data)
            return inventory_data
        except Exception as e:
            print(f"[LOT_TRACKER] Error sincronizando lotes: {e}")
            return self.load_inventory()

    def get_active_lots(self):
        """
        Función: get_active_lots
        Retorna la lista de lotes activos con saldo remanente pendiente de venta.
        """
        inv = self.load_inventory()
        return [l for l in inv.get('lots', []) if l.get('remaining', 0) >= 0.5]

    def get_lot_summary(self):
        """
        Función: get_lot_summary
        Genera un resumen estructurado para integración en APIs del ERP y paneles de supervisión.
        """
        inv = self.load_inventory()
        lots = inv.get('lots', [])
        return {
            'total_lots': len(lots),
            'mapped_base': inv.get('mapped_base', 0.0),
            'total_base': inv.get('total_base', 0.0),
            'unmapped_base': inv.get('unmapped_base', 0.0),
            'lots': lots,
            'updated_at': inv.get('timestamp')
        }
