#!/usr/bin/env python3
"""
Módulo: trade_notifier.py
Función: Notificador en tiempo real de operaciones de Grid Trading para Telegram.
Autor: Programador Senior Experto en Ciberseguridad
Descripción: Calcula la rentabilidad exacta por operación (bruto, comisiones, neto y %)
             así como el estado global de la cartera (ciclos cerrados, posiciones activas,
             P&L en dinero y porcentaje) y envía un informe detallado a Fran por Telegram.
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.parse
from datetime import datetime

TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
BASE_LOGS = "data"
TRADES_FILE = os.path.join(BASE_LOGS, "trades.json")
METRICS_FILE = os.path.join(BASE_LOGS, "metrics.json")
GRID_CONFIG = os.path.join(BASE_LOGS, "grid_config.json")
OPEN_ORDERS_FILE = os.path.join(BASE_LOGS, "open_orders.json")

def load_json(filepath, default=None):
    """
    Función: load_json
    Carga de forma segura un archivo JSON local.
    """
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        sys.stderr.write(f"[WARN] Error leyendo {filepath}: {e}\n")
    return default if default is not None else {}

def send_telegram_msg(text, parse_mode='HTML'):
    """
    Función: send_telegram_msg
    Envía el mensaje formateado a Telegram mediante la API oficial con reintento seguro.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': parse_mode
    }
    try:
        data_bytes = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status == 200
    except Exception as e:
        try:
            payload.pop('parse_mode', None)
            data_bytes = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data_bytes, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status == 200
        except Exception as e2:
            sys.stderr.write(f"[ERROR] Fallo al enviar mensaje Telegram: {e2}\n")
            return False

def calculate_global_stats(trades, grid_spacing=1.35):
    """
    Función: calculate_global_stats
    Calcula el historial completo de ciclos cerrados, beneficio neto, comisiones y P&L global.
    """
    spacing_mult = 1.0 + (grid_spacing / 100.0)
    margin_tolerance = grid_spacing * 0.015

    chron = sorted(trades, key=lambda x: str(x.get('timestamp') or x.get('datetime') or ''))
    pending_buys = []
    completed_pairs = []
    total_fees = 0.0

    for t in chron:
        side = t.get('side')
        p = float(t.get('price', 0))
        amt = float(t.get('amount', 0))
        fee = float(t.get('fee', {}).get('cost', 0)) if isinstance(t.get('fee'), dict) else 0.0
        total_fees += fee

        if side == 'buy':
            pending_buys.append({
                'price': p,
                'amount': amt,
                'remaining': amt,
                'fee': fee,
                'timestamp': t.get('timestamp') or t.get('datetime')
            })
        elif side == 'sell':
            sell_qty = amt
            while sell_qty >= 20.0 and pending_buys:
                best_idx = -1
                best_score = float('inf')
                for i, b in enumerate(pending_buys):
                    if b['remaining'] >= 20.0 and b['price'] < p:
                        expected = b['price'] * spacing_mult
                        diff = abs(p - expected) / b['price']
                        if diff < margin_tolerance and diff < best_score:
                            best_score = diff
                            best_idx = i
                if best_idx == -1:
                    for i, b in enumerate(pending_buys):
                        if b['remaining'] >= 20.0 and b['price'] < p:
                            diff = p - b['price']
                            if diff < best_score:
                                best_score = diff
                                best_idx = i
                if best_idx == -1:
                    break

                matched = pending_buys[best_idx]
                match_qty = min(matched['remaining'], sell_qty)
                gross = (p - matched['price']) * match_qty
                prop_buy_fee = (match_qty / matched['amount']) * matched['fee'] if matched['amount'] > 0 else 0
                prop_sell_fee = (match_qty / amt) * fee if amt > 0 else 0
                fees = prop_buy_fee + prop_sell_fee
                net = gross - fees
                cost = matched['price'] * match_qty
                gross_pct = ((p - matched['price']) / matched['price']) * 100 if matched['price'] > 0 else 0
                net_pct = (net / cost * 100) if cost > 0 else 0

                completed_pairs.append({
                    'buy_price': matched['price'],
                    'sell_price': p,
                    'qty': match_qty,
                    'cost': cost,
                    'gross': gross,
                    'net': net,
                    'pct': gross_pct,
                    'net_pct': net_pct,
                    'fees': fees
                })

                matched['remaining'] -= match_qty
                sell_qty -= match_qty
                if matched['remaining'] < 20.0:
                    pending_buys.pop(best_idx)

    total_net_pnl = sum(c['net'] for c in completed_pairs)
    wins = sum(1 for c in completed_pairs if c['net'] > 0)
    win_rate = (wins / len(completed_pairs) * 100) if completed_pairs else 100.0

    return {
        'completed': len(completed_pairs),
        'wins': wins,
        'win_rate': win_rate,
        'total_net_pnl': total_net_pnl,
        'total_fees': total_fees,
        'active_positions': len([b for b in pending_buys if b['remaining'] >= 20.0]),
        'last_pair': completed_pairs[-1] if completed_pairs else None
    }

def format_and_send_notification(side, price, amount, symbol="KAS/USDT"):
    """
    Función: format_and_send_notification
    Construye y envía el informe a Telegram con datos 100% sincronizados con el Dashboard ERP.
    """
    trades = load_json(TRADES_FILE, [])
    metrics = load_json(METRICS_FILE, {})
    config = load_json(GRID_CONFIG, {})
    spacing = float(config.get('spacing', 1.35))
    portfolio = metrics.get('portfolio', {})
    capital = float(portfolio.get('total_balance') or portfolio.get('total_value') or 126.0)

    # Intentar obtener estadísticas sincronizadas 1:1 desde el servidor ERP local
    dash_stats = None
    try:
        req = urllib.request.Request("http://127.0.0.1:5000/api/dashboard")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                dash_data = json.loads(resp.read().decode('utf-8'))
                dash_stats = dash_data.get('trade_stats')
                dash_port = dash_data.get('portfolio')
                if dash_port and dash_port.get('total_balance'):
                    capital = float(dash_port['total_balance'])
    except Exception:
        pass

    stats = calculate_global_stats(trades, spacing)
    base_coin = symbol.split('/')[0]
    total_cost = price * amount

    # Valores consistentes con el ERP
    if dash_stats:
        pnl_val = dash_stats.get('total_pnl', stats['total_net_pnl'])
        completed_cycles = dash_stats.get('completed', stats['completed'])
        win_rate = dash_stats.get('win_rate', 1.0) * 100
        active_positions = dash_stats.get('active', stats['active_positions'])
    else:
        pnl_val = stats['total_net_pnl']
        completed_cycles = stats['completed']
        win_rate = stats['win_rate']
        active_positions = stats['active_positions']

    initial_capital = 16.0
    pnl_pct = (pnl_val / initial_capital * 100) if initial_capital > 0 else 0.0
    pnl_sign = '+' if pnl_val >= 0 else ''

    if side.lower() == 'sell':
        last_pair = stats.get('last_pair') or {}
        buy_p = last_pair.get('buy_price', price / (1.0 + spacing/100.0))
        op_gross = last_pair.get('gross', (price - buy_p) * amount)
        op_fees = last_pair.get('fees', 0.0222)
        op_net = last_pair.get('net', op_gross - op_fees)
        op_gross_pct = last_pair.get('pct', ((price - buy_p) / buy_p) * 100 if buy_p > 0 else spacing)
        op_cost = buy_p * amount
        op_net_pct = (op_net / op_cost * 100) if op_cost > 0 else (op_gross_pct - 0.40)

        msg = (
            f"🎉 <b>¡CICLO COMPLETADO EN KUCOIN! ({symbol})</b>\n\n"
            f"🔴 <b>VENTA EJECUTADA:</b>\n"
            f"• <b>Vendido:</b> <code>{amount:.4f} {base_coin}</code> @ <b>${price:.5f}</b>\n"
            f"• <b>Importe cobrado:</b> <code>${total_cost:.4f} USDT</code>\n"
            f"• <b>Compra origen:</b> @ ${buy_p:.5f}\n"
            f"• <b>Margen bruto:</b> +{op_gross_pct:.2f}%\n\n"
            f"💰 <b>RENTABILIDAD DE LA OPERACIÓN:</b>\n"
            f"• <b>Bruto:</b> +${op_gross:.4f} USDT (+{op_gross_pct:.2f}%)\n"
            f"• <b>Comisiones:</b> -${op_fees:.4f} USDT\n"
            f"• <b>Beneficio Neto:</b> <b>+{op_net:.4f} USDT (+{op_net_pct:.2f}%)</b>\n\n"
            f"📊 <b>ESTADO GLOBAL DEL BOT:</b>\n"
            f"• <b>Ciclos cerrados:</b> {completed_cycles} (Win Rate: {win_rate:.1f}%)\n"
            f"• <b>Posiciones activas:</b> {active_positions} en libro\n"
            f"• <b>P&L Global Neto:</b> <b>{pnl_sign}${pnl_val:.4f} USDT ({pnl_sign}{pnl_pct:.2f}%)</b>\n"
            f"• <b>Capital total:</b> ${capital:.2f} USDT\n\n"
            f"<i>¡Beneficio asegurado, Fran! Seguimos vigilando la cuadrícula.</i>"
        )
    else:
        target_sell_p = round(price * (1.0 + spacing / 100.0), 5)
        proj_gain = (target_sell_p - price) * amount

        msg = (
            f"🟢 <b>NUEVA COMPRA EN EL GRID ({symbol})</b>\n\n"
            f"📦 <b>DETALLE DE ENTRADA:</b>\n"
            f"• <b>Comprado:</b> <code>{amount:.4f} {base_coin}</code> @ <b>${price:.5f}</b>\n"
            f"• <b>Inversión:</b> <code>${total_cost:.4f} USDT</code>\n"
            f"• <b>Contra-orden SELL:</b> {amount * 0.998:.4f} {base_coin} @ <b>${target_sell_p:.5f}</b>\n"
            f"• <b>Margen objetivo:</b> +{spacing:.2f}% (+${proj_gain:.4f} USDT)\n\n"
            f"📊 <b>ESTADO GLOBAL:</b>\n"
            f"• <b>Posiciones activas:</b> {active_positions} en curso\n"
            f"• <b>Ciclos cerrados:</b> {completed_cycles}\n"
            f"• <b>P&L Acumulado:</b> <b>{pnl_sign}${pnl_val:.4f} USDT ({pnl_sign}{pnl_pct:.2f}%)</b>\n"
            f"• <b>Capital total:</b> ${capital:.2f} USDT\n\n"
            f"<i>Posición capturada en nivel de rejilla, Fran. Esperando el rebote.</i>"
        )

    return send_telegram_msg(msg)

def main():
    """
    Función: main
    Punto de entrada para ejecución por línea de comandos o subproceso desde grid_bot.
    """
    parser = argparse.ArgumentParser(description="Notificador de trades a Telegram para Hermes.")
    parser.add_argument("--side", required=True, choices=["buy", "sell"], help="Lado de la operación: buy o sell")
    parser.add_argument("--price", type=float, required=True, help="Precio de ejecución")
    parser.add_argument("--amount", type=float, required=True, help="Cantidad ejecutada")
    parser.add_argument("--symbol", default="KAS/USDT", help="Par de trading")
    args = parser.parse_args()

    ok = format_and_send_notification(args.side, args.price, args.amount, args.symbol)
    if ok:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Notificación {args.side.upper()} enviada a Telegram con éxito.")
    else:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Error al enviar notificación a Telegram.")

if __name__ == "__main__":
    main()
