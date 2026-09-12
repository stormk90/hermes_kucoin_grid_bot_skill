/**
 * Función: fetchLivePrice - Consulta el precio actual de la criptomoneda seleccionada y actualiza la cabecera.
 */
async function fetchLivePrice() {
    try {
        const resp = await fetch(`/api/chart/candles?coin=${currentCoin}&live=true`);
        const data = await resp.json();
        if (data && data.current_price) {
            currentLivePrice = data.current_price;
            const price = data.current_price;
            const priceEl = document.getElementById('headerPrice');
            const changeEl = document.getElementById('headerChange');
            if (priceEl) priceEl.textContent = formatCurrency(price, 5);
            if (changeEl && data.stats) {
                const change = data.stats.change_pct_72h || 0;
                changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
                changeEl.className = 'price-change ' + (change >= 0 ? 'positive' : 'negative');
            }
        }
    } catch (e) {
        console.warn('Aviso en actualización de precio en vivo:', e);
    }
}

/**
 * Función: loadMetrics - Carga métricas globales del bot, portafolio y operaciones realizadas.
 */
async function loadMetrics() {
    try {
        const [dashResp, tradesResp, ordersResp] = await Promise.all([
            fetch('/api/dashboard'),
            fetch('/api/trades'),
            fetch('/api/orders/active')
        ]);
        
        const dash = await dashResp.json();
        const tradesData = await tradesResp.json();
        const ordersData = await ordersResp.json();

        if (ordersData && ordersData.orders) {
            cachedOpenOrders = ordersData.orders;
        }

        const stats = dash.trade_stats || {};
        const cap = dash.portfolio?.total_balance || 0;
        
        const metricCap = document.getElementById('metricCapital');
        if (metricCap) metricCap.textContent = '$' + cap.toFixed(2);

        const metricPnl = document.getElementById('metricPnl');
        if (metricPnl) {
            const pnl = (stats.total_pnl !== undefined) ? stats.total_pnl : (stats.net_pnl || 0);
            const gross = stats.gross_pnl || 0;
            const fees = stats.total_fees || 0;
            const sign = pnl >= 0 ? '+' : '';
            
            // Rentabilidad Ponderada (TWR): preserva el rendimiento real sobre el capital con el que operó el bot ($16)
            const initialCapital = 16.0;
            const twrPct = initialCapital > 0 ? (pnl / initialCapital) * 100 : 0;
            const dilutedPct = cap > 0 ? (pnl / cap) * 100 : 0;
            const pnlColor = pnl >= 0 ? '#3fb950' : '#f85149';
            metricPnl.innerHTML = `${sign}$${pnl.toFixed(4)} <span style="font-size:13px;font-weight:600;color:${pnlColor};opacity:0.85;">(${sign}${twrPct.toFixed(2)}%)</span>`;
            metricPnl.className = 'metric-value ' + (pnl >= 0 ? 'positive' : 'negative');
            metricPnl.title = `Rentabilidad Real (TWR): ${sign}${twrPct.toFixed(2)}% sobre capital operativo inicial ($${initialCapital.toFixed(2)} USDT)\nDiluido sobre balance actual ($${cap.toFixed(2)} USDT): ${sign}${dilutedPct.toFixed(2)}%\nP&L Neto: ${sign}$${pnl.toFixed(4)} USDT | Bruto: +$${gross.toFixed(4)} | Comisiones: -$${fees.toFixed(4)} USDT`;
        }

        const metricWinRate = document.getElementById('metricWinRate');
        if (metricWinRate) {
            const wr = (stats.win_rate !== undefined) ? (stats.win_rate * 100) : 0;
            const avgPct = (stats.avg_profit_pct !== undefined) ? stats.avg_profit_pct : 0;
            const avgSign = avgPct >= 0 ? '+' : '';
            const avgColor = avgPct >= 0 ? '#3fb950' : '#f85149';
            if (avgPct > 0) {
                metricWinRate.innerHTML = `${wr.toFixed(0)}% <span style="font-size:13px;font-weight:600;color:${avgColor};opacity:0.85;">(${avgSign}${avgPct.toFixed(2)}%/op)</span>`;
            } else {
                metricWinRate.textContent = wr.toFixed(1) + '%';
            }
            metricWinRate.className = 'metric-value ' + (wr >= 50 ? 'positive' : 'negative');
            metricWinRate.title = `Win Rate: ${wr.toFixed(1)}% (${stats.wins || 0} ganadoras de ${stats.completed || 0} completadas)\nRentabilidad media neta por operación: ${avgSign}${avgPct.toFixed(2)}%`;
        }

        cachedRawTrades = tradesData.trades || [];

        // Cálculo de rentabilidad media por día desde el inicio
        let daysActive = 1.0;
        if (cachedRawTrades.length > 0) {
            const timestamps = cachedRawTrades.map(t => new Date(t.timestamp).getTime()).filter(t => !isNaN(t));
            if (timestamps.length > 0) {
                const minTs = Math.min(...timestamps);
                const diffDays = (Date.now() - minTs) / (1000 * 60 * 60 * 24);
                daysActive = Math.max(diffDays, 0.5);
            }
        }

        const pnlVal = (stats.total_pnl !== undefined) ? stats.total_pnl : (stats.net_pnl || 0);
        const dailyPnlUsdt = pnlVal / daysActive;
        const initialCapital = 16.0;
        const dailyTwrPct = initialCapital > 0 ? (dailyPnlUsdt / initialCapital) * 100 : 0;
        const dailyDilutedPct = cap > 0 ? (dailyPnlUsdt / cap) * 100 : 0;
        const dailySign = dailyPnlUsdt >= 0 ? '+' : '';
        const dailyColor = dailyPnlUsdt >= 0 ? '#3fb950' : '#f85149';

        const metricDaily = document.getElementById('metricDailyPnl');
        if (metricDaily) {
            metricDaily.innerHTML = `${dailySign}$${dailyPnlUsdt.toFixed(4)} <span style="font-size:13px;font-weight:600;color:${dailyColor};opacity:0.85;">(${dailySign}${dailyTwrPct.toFixed(2)}%/d)</span>`;
            metricDaily.className = 'metric-value ' + (dailyPnlUsdt >= 0 ? 'positive' : 'negative');
            metricDaily.title = `Rentabilidad Media: ${dailySign}$${dailyPnlUsdt.toFixed(4)} USDT/día (${dailySign}${dailyTwrPct.toFixed(2)}%/d sobre capital operativo de $${initialCapital.toFixed(2)})\nDiluido sobre balance actual ($${cap.toFixed(2)}): ${dailySign}${dailyDilutedPct.toFixed(2)}%/d en ${daysActive.toFixed(2)} días`;
        }

        renderPairedOperations(cachedRawTrades);
    } catch (err) {
        console.error('Error al cargar métricas del bot:', err);
    }
}

/**
 * Función: renderPairedOperations
 * Renderiza el listado de operaciones reales de KuCoin 1:1, mostrando para cada venta
 * a cuánto se compró, a cuánto se vendió y el beneficio neto real en USDT y en porcentaje.
 * Mantiene cada orden como una única fila real del exchange sin partir cantidades.
 */
function renderPairedOperations(rawTrades) {
    const tbody = document.getElementById('operationsTableBody');
    if (!tbody) return;

    if (!rawTrades || rawTrades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#8b949e;padding:20px;">No hay operaciones registradas aún.</td></tr>';
        return;
    }

    // Consolidar por orden real de KuCoin (1 orden en exchange = 1 fila en panel)
    const ordersMap = new Map();
    [...rawTrades].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp)).forEach(t => {
        const oid = t.order_id || t.id;
        const amt = parseFloat(t.amount) || 0;
        const price = parseFloat(t.price) || 0;
        const cost = parseFloat(t.cost) || (amt * price);
        const fee = (t.fee && t.fee.cost) ? parseFloat(t.fee.cost) : 0.0021;

        if (!ordersMap.has(oid)) {
            ordersMap.set(oid, {
                id: t.id,
                order_id: oid,
                timestamp: t.timestamp,
                symbol: t.symbol || 'KAS/USDT',
                side: t.side,
                amount: amt,
                cost: cost,
                price: price,
                feeCost: fee
            });
        } else {
            const existing = ordersMap.get(oid);
            const newAmt = existing.amount + amt;
            existing.cost += cost;
            existing.price = newAmt > 0 ? (existing.cost / newAmt) : price;
            existing.amount = newAmt;
            existing.feeCost += fee;
        }
    });

    // Trazabilidad contable por niveles del Grid: cada venta cierra la compra de su escalón inferior
    const chronOrders = Array.from(ordersMap.values()).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    const pendingBuys = [];

    chronOrders.forEach(o => {
        if (o.side === 'buy') {
            pendingBuys.push({
                amount: o.amount,
                remaining: o.amount,
                price: o.price,
                cost: o.cost,
                feeCost: o.feeCost
            });
            o.buyPrice = o.price;
            o.sellPrice = null;
            o.pnlUsdt = null;
            o.pnlPct = null;
        } else if (o.side === 'sell') {
            let needed = o.amount;
            const matchedBuys = [];

            // Buscar compras previas abiertas con precio inferior al de venta, priorizando el nivel más cercano por debajo
            while (needed > 0.0001) {
                const candidates = pendingBuys.filter(b => b.remaining > 0.0001 && b.price < o.price);
                if (candidates.length === 0) break;

                // Ordenar por precio descendente (la compra inmediatamente inferior en el escalón del Grid)
                candidates.sort((a, b) => b.price - a.price);
                const bestBuy = candidates[0];

                const take = Math.min(needed, bestBuy.remaining);
                const propCost = take * bestBuy.price;
                const propFee = (bestBuy.amount > 0) ? ((take / bestBuy.amount) * bestBuy.feeCost) : 0;

                matchedBuys.push({
                    amount: take,
                    cost: propCost,
                    fee: propFee
                });

                bestBuy.remaining -= take;
                needed -= take;
            }

            if (matchedBuys.length > 0) {
                const totAmt = matchedBuys.reduce((sum, m) => sum + m.amount, 0);
                const totCost = matchedBuys.reduce((sum, m) => sum + m.cost, 0);
                const totBuyFee = matchedBuys.reduce((sum, m) => sum + m.fee, 0);

                o.buyPrice = totAmt > 0 ? (totCost / totAmt) : null;
                o.sellPrice = o.price;
                const grossPnl = (o.price * totAmt) - totCost;
                const totFees = (o.feeCost + totBuyFee);
                const netPnl = grossPnl - totFees;

                o.grossPnl = grossPnl;
                o.grossPct = totCost > 0 ? ((grossPnl / totCost) * 100) : 0;
                o.buyFee = totBuyFee;
                o.sellFee = o.feeCost;
                o.totalFees = totFees;

                o.pnlUsdt = netPnl;
                o.netPct = totCost > 0 ? ((netPnl / totCost) * 100) : 0;
                o.pnlPct = o.netPct;
            } else {
                o.buyPrice = null;
                o.sellPrice = o.price;
                o.pnlUsdt = null;
                o.pnlPct = null;
                o.netPct = null;
                o.grossPnl = null;
                o.grossPct = null;
                o.totalFees = null;
            }
        }
    });

    const allOrders = chronOrders;
    const buyOrders = allOrders.filter(o => o.side === 'buy');
    const sellOrders = allOrders.filter(o => o.side === 'sell');

    // Métricas exactas reales
    const metricTrades = document.getElementById('metricTrades');
    if (metricTrades) {
        let daysActive = 1.0;
        if (allOrders.length > 0) {
            const timestamps = allOrders.map(t => new Date(t.timestamp).getTime()).filter(t => !isNaN(t));
            if (timestamps.length > 0) {
                const minTs = Math.min(...timestamps);
                const diffDays = (Date.now() - minTs) / (1000 * 60 * 60 * 24);
                daysActive = Math.max(diffDays, 0.5);
            }
        }
        metricTrades.innerHTML = `${allOrders.length} <span style="font-size:12px;color:#8b949e;font-weight:normal;">(${daysActive.toFixed(1)}d · ${sellOrders.length}v/${buyOrders.length}c)</span>`;
        metricTrades.title = `${allOrders.length} órdenes ejecutadas en KuCoin (${buyOrders.length} compras, ${sellOrders.length} ventas) en ${daysActive.toFixed(2)} días`;
    }

    // Cálculo de rentabilidad en las últimas 24 horas (Rentabilidad Último Día)
    const metricLastDay = document.getElementById('metricLastDayPnl');
    if (metricLastDay) {
        const ms24h = Date.now() - (24 * 60 * 60 * 1000);
        const pnl24h = allOrders
            .filter(o => o.pnlUsdt !== null && o.timestamp && new Date(o.timestamp).getTime() >= ms24h)
            .reduce((sum, o) => sum + o.pnlUsdt, 0);

        const capEl = document.getElementById('metricCapital');
        const currentCap = capEl ? (parseFloat(capEl.textContent.replace('$', '')) || 126.90) : 126.90;
        const baseCapital24h = 16.0;
        const pct24h = baseCapital24h > 0 ? (pnl24h / baseCapital24h) * 100 : 0;
        const sign24 = pnl24h >= 0 ? '+' : '';
        const color24 = pnl24h >= 0 ? '#3fb950' : '#f85149';

        metricLastDay.innerHTML = `${sign24}$${pnl24h.toFixed(4)} <span style="font-size:13px;font-weight:600;color:${color24};opacity:0.85;">(${sign24}${pct24h.toFixed(2)}%)</span>`;
        metricLastDay.className = 'metric-value ' + (pnl24h >= 0 ? 'positive' : 'negative');
        metricLastDay.title = `Beneficio neto últimas 24 horas: ${sign24}$${pnl24h.toFixed(4)} USDT (${sign24}${pct24h.toFixed(2)}% sobre capital de $${baseCapital24h.toFixed(2)} de ese período)\nDiluido sobre balance actual ($${currentCap.toFixed(2)}): ${sign24}${(pnl24h / currentCap * 100).toFixed(2)}%`;
    }

    // Cálculo de rentabilidad media por operación (%) y Win Rate en base a órdenes reales
    const metricWinRateEl = document.getElementById('metricWinRate');
    if (metricWinRateEl) {
        const closedSales = sellOrders.filter(o => o.pnlPct !== null && o.pnlPct !== undefined);
        if (closedSales.length > 0) {
            const wins = closedSales.filter(o => (o.pnlUsdt || 0) >= 0);
            const winRatePct = (wins.length / closedSales.length) * 100;
            const avgNetPct = closedSales.reduce((sum, o) => sum + o.pnlPct, 0) / closedSales.length;
            const avgGrossPct = closedSales.reduce((sum, o) => sum + (o.grossPct || 0), 0) / closedSales.length;
            const avgSign = avgNetPct >= 0 ? '+' : '';
            const avgColor = avgNetPct >= 0 ? '#3fb950' : '#f85149';
            metricWinRateEl.innerHTML = `${winRatePct.toFixed(0)}% <span style="font-size:13px;font-weight:600;color:${avgColor};opacity:0.85;">(${avgSign}${avgNetPct.toFixed(2)}%/op)</span>`;
            metricWinRateEl.className = 'metric-value ' + (winRatePct >= 50 ? 'positive' : 'negative');
            metricWinRateEl.title = `Win Rate: ${winRatePct.toFixed(1)}% (${wins.length} ganadoras de ${closedSales.length} ventas)\nRentabilidad media neta: ${avgSign}${avgNetPct.toFixed(2)}% por operación (${avgSign}${avgGrossPct.toFixed(2)}% bruto antes de comisiones)`;
        }
    }

    // Actualizar badges de pestañas
    const tabAll = document.querySelector('.tab-btn[data-tab="all"]');
    const tabAct = document.querySelector('.tab-btn[data-tab="active"]');
    const tabComp = document.querySelector('.tab-btn[data-tab="completed"]');
    if (tabAll) tabAll.textContent = `Todas (${allOrders.length})`;
    if (tabAct) tabAct.textContent = `Compras (${buyOrders.length})`;
    if (tabComp) tabComp.textContent = `Ventas (${sellOrders.length})`;

    let filtered = allOrders;
    if (currentTradeTab === 'active') {
        filtered = buyOrders; // Pestaña Compras
    } else if (currentTradeTab === 'completed') {
        filtered = sellOrders; // Pestaña Ventas
    }

    // Ordenar de más reciente a más antigua
    filtered = [...filtered].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    // Paginación
    const totalTrades = filtered.length;
    const totalPages = Math.ceil(totalTrades / TRADE_PAGE_SIZE) || 1;
    if (currentTradePage > totalPages) currentTradePage = totalPages;
    if (currentTradePage < 1) currentTradePage = 1;

    const pageInfoEl = document.getElementById('operationsPageInfo');
    const pageCounterEl = document.getElementById('operationsPageCounter');
    const btnPrev = document.getElementById('btnPrevTradePage');
    const btnNext = document.getElementById('btnNextTradePage');

    if (totalTrades === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#8b949e;padding:16px;">No hay registros para este filtro.</td></tr>';
        if (pageInfoEl) pageInfoEl.textContent = 'Mostrando 0 de 0 operaciones';
        if (pageCounterEl) pageCounterEl.textContent = 'Página 1 de 1';
        if (btnPrev) { btnPrev.disabled = true; btnPrev.style.opacity = '0.5'; btnPrev.style.cursor = 'not-allowed'; }
        if (btnNext) { btnNext.disabled = true; btnNext.style.opacity = '0.5'; btnNext.style.cursor = 'not-allowed'; }
        return;
    }

    const startIdx = (currentTradePage - 1) * TRADE_PAGE_SIZE;
    const endIdx = Math.min(startIdx + TRADE_PAGE_SIZE, totalTrades);
    const pagedTrades = filtered.slice(startIdx, endIdx);

    if (pageInfoEl) pageInfoEl.textContent = `Mostrando ${startIdx + 1}-${endIdx} de ${totalTrades} operaciones`;
    if (pageCounterEl) pageCounterEl.textContent = `Página ${currentTradePage} de ${totalPages}`;
    if (btnPrev) {
        btnPrev.disabled = (currentTradePage <= 1);
        btnPrev.style.opacity = (currentTradePage <= 1) ? '0.5' : '1';
        btnPrev.style.cursor = (currentTradePage <= 1) ? 'not-allowed' : 'pointer';
    }
    if (btnNext) {
        btnNext.disabled = (currentTradePage >= totalPages);
        btnNext.style.opacity = (currentTradePage >= totalPages) ? '0.5' : '1';
        btnNext.style.cursor = (currentTradePage >= totalPages) ? 'not-allowed' : 'pointer';
    }

    tbody.innerHTML = pagedTrades.map(o => {
        const isBuy = (o.side === 'buy');
        const dateStr = o.timestamp ? new Date(o.timestamp).toLocaleString('es-ES') : '—';
        const typeHtml = isBuy
            ? '<span class="badge-side badge-buy" style="font-weight:700;">🟢 COMPRA</span>'
            : '<span class="badge-side badge-sell" style="font-weight:700;color:#f85149;border-color:#da3633;">🔴 VENTA</span>';
        
        const buyPriceStr = (o.buyPrice !== null && o.buyPrice !== undefined) ? formatCurrency(o.buyPrice, 5) : '—';
        const sellPriceStr = (o.sellPrice !== null && o.sellPrice !== undefined) ? formatCurrency(o.sellPrice, 5) : '—';
        const amountStr = `${o.amount.toFixed(4)} KAS`;
        const costStr = `$${o.cost.toFixed(4)} USDT`;
        const feeStr = `$${o.feeCost.toFixed(4)} USDT`;
        
        let pnlHtml = '<span style="color:#8b949e;font-size:12px;">— (Entrada)</span>';
        let pnlTdTitle = '';
        if (!isBuy && o.pnlUsdt !== null && o.pnlUsdt !== undefined) {
            const isProfit = (o.pnlUsdt >= 0);
            const sign = isProfit ? '+' : '';
            const pnlColor = isProfit ? '#3fb950' : '#f85149';
            const grossSign = (o.grossPnl >= 0 ? '+' : '');
            pnlTdTitle = `Beneficio Limpio (Neto): ${sign}$${o.pnlUsdt.toFixed(4)} (${sign}${o.netPct.toFixed(2)}%)\nBruto sin comisiones: ${grossSign}$${o.grossPnl.toFixed(4)} (${grossSign}${o.grossPct.toFixed(2)}%)\nComisiones KuCoin: -$${o.totalFees.toFixed(4)} USDT (Venta: -$${o.sellFee.toFixed(4)}, Compra: -$${o.buyFee.toFixed(4)})`;
            pnlHtml = `<span style="font-weight:700;color:${pnlColor};cursor:help;" title="${pnlTdTitle}">${sign}$${o.pnlUsdt.toFixed(4)} <span style="font-size:11px;opacity:0.9;">(${sign}${o.netPct.toFixed(2)}% neto)</span></span>`;
        }

        let feeHtml = `<span style="color:#8b949e;font-size:12px;">${feeStr}</span>`;
        if (!isBuy && o.totalFees !== null && o.totalFees !== undefined) {
            const feeTooltip = `Comisión de Venta: $${o.sellFee.toFixed(4)} USDT\nComisión de Compra asociada: $${o.buyFee.toFixed(4)} USDT\nTotal comisiones ciclo: $${o.totalFees.toFixed(4)} USDT`;
            feeHtml = `<span style="color:#8b949e;font-size:12px;cursor:help;" title="${feeTooltip}">$${o.feeCost.toFixed(4)} <span style="font-size:10px;opacity:0.8;">(tot: $${o.totalFees.toFixed(4)})</span></span>`;
        }

        const statusHtml = '<span class="badge-side badge-buy" style="font-size:10px;">✅ COMPLETADO</span>';

        return `
            <tr>
                <td style="color:#8b949e;font-size:12px;">${dateStr}</td>
                <td>${typeHtml}</td>
                <td style="font-weight:600;color:#3fb950;">${buyPriceStr}</td>
                <td style="font-weight:600;color:${isBuy ? '#8b949e' : '#f85149'};">${sellPriceStr}</td>
                <td style="font-weight:600;color:#e6edf3;">${amountStr}</td>
                <td style="font-weight:700;color:#58a6ff;">${costStr}</td>
                <td title="${pnlTdTitle}">${pnlHtml}</td>
                <td>${feeHtml}</td>
                <td style="text-align:right;">${statusHtml}</td>
            </tr>
        `;
    }).join('');
}

/**
 * Función: switchTradeTab - Cambia el filtro de la tabla de operaciones (Todas, Activas, Completadas) y resetea el paginador a la primera página.
 */
function switchTradeTab(tab) {
    currentTradeTab = tab;
    currentTradePage = 1;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    const activeBtn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
    if (activeBtn) activeBtn.classList.add('active');
    loadMetrics();
}

/**
 * Función: changeTradePage - Navega entre páginas de operaciones (adelante o atrás) y refresca la tabla.
 */
function changeTradePage(delta) {
    currentTradePage += delta;
    if (currentTradePage < 1) currentTradePage = 1;
    if (cachedRawTrades && cachedRawTrades.length > 0) {
        renderPairedOperations(cachedRawTrades);
    }
}

/**
 * Función: loadActiveOrders - Consulta órdenes vivas en KuCoin y actualiza la sección de Grid & Órdenes en Curso.
 */
async function loadActiveOrders() {
    try {
        const resp = await fetch('/api/orders/active');
        const data = await resp.json();
        if (!data || !data.orders) return;

        cachedOpenOrders = data.orders;
        const stats = data.stats || {};
        const orders = data.orders;
        const buys = orders.filter(o => o.type === 'compra');
        const sells = orders.filter(o => o.type === 'venta');

        const curPriceEl = document.getElementById('gridCurrentPrice');
        if (curPriceEl) curPriceEl.textContent = formatCurrency(data.current_price, 5);

        const minPriceEl = document.getElementById('gridMinPrice');
        if (minPriceEl) minPriceEl.textContent = formatCurrency(data.grid_min, 5);

        const maxPriceEl = document.getElementById('gridMaxPrice');
        if (maxPriceEl) maxPriceEl.textContent = formatCurrency(data.grid_max, 5);

        const stopLossPrice = data.stop_loss_price || (data.grid_min * 0.95);
        const stopLossPct = data.stop_loss_pct || 5.0;
        if (data.stop_loss_mode) currentStopLossMode = data.stop_loss_mode;
        const stopLossEl = document.getElementById('gridStopLoss');
        const stopLossLabel = document.getElementById('gridStopLossLabel');
        if (stopLossEl) {
            if (currentStopLossMode === 'hold') {
                if (stopLossLabel) stopLossLabel.textContent = '🛡️ Protección Spot:';
                stopLossEl.innerHTML = `<span style="color:#58a6ff;">Hold &amp; Rebound</span> <span style="font-size:11px;color:#8b949e;font-weight:normal;">(Suelo $${stopLossPrice})</span>`;
                stopLossEl.title = `Modo Hold & Rebound activo: Nunca malvenderá en pérdidas en spot. Si el precio cae por debajo de $${stopLossPrice} (-${stopLossPct}%), el bot pausará compras y esperará el rebote.`;
            } else {
                if (stopLossLabel) stopLossLabel.textContent = '⚡ Stop-Loss Mercado:';
                stopLossEl.innerHTML = `<span style="color:#f85149;">${formatCurrency(stopLossPrice, 5)}</span> <span style="font-size:11px;color:#f85149;opacity:0.85;">(-${stopLossPct}%)</span>`;
                stopLossEl.title = `Modo Venta a Mercado activo: Si el precio toca $${stopLossPrice} (-${stopLossPct}%), cancelará órdenes y liquidará a mercado.`;
            }
        }

        const posPctEl = document.getElementById('gridPositionPct');
        if (posPctEl) posPctEl.textContent = (stats.grid_position_pct || 0).toFixed(1) + '%';
        const buyCountEl = document.getElementById('gridBuyCount');
        if (buyCountEl) buyCountEl.textContent = stats.total_buy_orders || buys.length;
        const sellCountEl = document.getElementById('gridSellCount');
        if (sellCountEl) sellCountEl.textContent = stats.total_sell_orders || sells.length;

        const barFill = document.getElementById('gridProgressFill');
        if (barFill) barFill.style.width = Math.max(0, Math.min(100, stats.grid_position_pct || 50)) + '%';

        const tbody = document.getElementById('activeOrdersTableBody');
        if (tbody) {
            if (orders.length === 0) {
                tbody.innerHTML = '<tr><td colspan="9" style="text-align:center;color:#8b949e;padding:16px;">No hay órdenes activas actualmente en KuCoin.</td></tr>';
            } else {
                const currentPrice = parseFloat(data.current_price) || currentLivePrice || 0;
                tbody.innerHTML = orders.map((o, idx) => {
                    const isBuy = (o.type === 'compra');
                    const sideBadge = isBuy ? '<span class="badge-side badge-buy">COMPRA</span>' : '<span class="badge-side badge-sell">VENTA</span>';
                    const cancelBtnHtml = o.id ? `<button class="btn-cancel-order" onclick="triggerCancelOrder('${o.id}', '${o.type}', ${o.price}, ${o.quantity})" type="button">✕ Quitar</button>` : '—';
                    
                    let diffHtml = '<span style="color:#8b949e;">—</span>';
                    if (currentPrice > 0 && o.price > 0) {
                        const diffPct = ((o.price - currentPrice) / currentPrice) * 100;
                        const sign = diffPct >= 0 ? '+' : '';
                        const color = isBuy ? '#3fb950' : '#f85149';
                        const actionDesc = isBuy ? `caída del ${Math.abs(diffPct).toFixed(2)}%` : `subida del ${Math.abs(diffPct).toFixed(2)}%`;
                        diffHtml = `<span style="font-weight:700;font-family:'SF Mono',Consolas,monospace;color:${color};" title="Falta una ${actionDesc} desde el precio actual (${formatCurrency(currentPrice, 5)}) para ejecutarse en KuCoin">${sign}${diffPct.toFixed(2)}%</span>`;
                    }

                    // Renderizado de Margen y Ganancia Estimada para órdenes de venta
                    let profitHtml = '<span style="color:#8b949e;font-size:11px;">Pendiente de ejecución</span>';
                    if (!isBuy) {
                        if (o.spacing_pct !== null && o.spacing_pct !== undefined && o.est_net_pnl !== null && o.est_net_pnl !== undefined) {
                            const originPriceStr = o.origin_buy_price ? `$${parseFloat(o.origin_buy_price).toFixed(5)}` : 'Compra previa';
                            const pnlSign = o.est_net_pnl >= 0 ? '+' : '';
                            const pnlColor = o.est_net_pnl >= 0 ? '#3fb950' : '#f85149';
                            profitHtml = `
                                <div style="display:flex;flex-direction:column;gap:2px;">
                                    <div style="display:flex;align-items:center;gap:6px;">
                                        <span style="font-weight:700;color:#58a6ff;background:rgba(88,166,255,0.12);padding:1px 5px;border-radius:3px;font-size:11px;" title="Margen programado sobre la compra de ${originPriceStr}">+${o.spacing_pct.toFixed(2)}%</span>
                                        <span style="font-weight:700;color:${pnlColor};font-size:12px;" title="Ganancia neta estimada tras comisiones de compra y venta (0.2%)">${pnlSign}$${o.est_net_pnl.toFixed(4)} <span style="font-size:10px;opacity:0.85;">(${pnlSign}${o.est_pnl_pct.toFixed(2)}%)</span></span>
                                    </div>
                                    <span style="font-size:10px;color:#8b949e;" title="Precio de compra de origen al que se adquirió este lote">Origen compra: ${originPriceStr}</span>
                                </div>`;
                        } else {
                            profitHtml = `<span style="color:#58a6ff;font-weight:600;font-size:11px;">+${currentGridSpacing.toFixed(2)}%</span>`;
                        }
                    } else {
                        // Para compras: indicar el objetivo de venta que se activará cuando se ejecute
                        const targetSellPrice = o.price * (1.0 + (currentGridSpacing / 100.0));
                        profitHtml = `<span style="color:#8b949e;font-size:11px;" title="Al ejecutarse la compra, colocará venta inmediata a este precio">Venta obj: <strong style="color:#c9d1d9;">${formatCurrency(targetSellPrice, 5)}</strong> (+${currentGridSpacing.toFixed(2)}%)</span>`;
                    }

                    return `
                        <tr>
                            <td style="color:#8b949e;">#${idx + 1}</td>
                            <td>${sideBadge}</td>
                            <td style="font-weight:700;color:${isBuy ? '#3fb950' : '#f85149'};">${formatCurrency(o.price, 5)}</td>
                            <td>${diffHtml}</td>
                            <td>${parseFloat(o.quantity).toFixed(2)}</td>
                            <td>$${parseFloat(o.value_usdt).toFixed(2)}</td>
                            <td>${profitHtml}</td>
                            <td><span class="badge-side badge-done">ACTIVA EN EXCHANGE</span></td>
                            <td style="text-align:right;">${cancelBtnHtml}</td>
                        </tr>`;
                }).join('');
            }
        }
    } catch (err) {
        console.error('Error al cargar órdenes activas:', err);
    }
}

/**
 * PANEL DE CONTROL DE ESTRATEGIAS (GRID BOT)
 */

/**
 * Función: loadStrategyConfig - Consulta la configuración activa del grid y actualiza el formulario y estado.
 */
async function loadStrategyConfig() {
    try {
        const resp = await fetch('/api/grid/strategy');
        const data = await resp.json();
        if (!data) return;

        // Cargar par y campos de configuración limpios
        if (data.symbol && document.getElementById('stratSymbol')) {
            document.getElementById('stratSymbol').value = data.symbol;
        }
        const minVal = parseFloat(data.grid_min || 0.033);
        const maxVal = parseFloat(data.grid_max || 0.041);
        const dec = (minVal < 1.0) ? 5 : ((minVal > 50) ? 2 : 4);

        const slVal = data.stop_loss_price || (minVal * 0.95);
        if (document.getElementById('stratGridMin')) document.getElementById('stratGridMin').value = minVal.toFixed(dec);
        if (document.getElementById('stratGridMax')) document.getElementById('stratGridMax').value = maxVal.toFixed(dec);
        if (document.getElementById('stratSpacing')) document.getElementById('stratSpacing').value = data.spacing || 1.35;
        if (document.getElementById('stratLevels')) document.getElementById('stratLevels').value = data.num_levels || 8;
        if (document.getElementById('stratCapital')) document.getElementById('stratCapital').value = data.capital || 16.0;
        if (document.getElementById('stratStopLoss')) document.getElementById('stratStopLoss').value = slVal.toFixed(dec);
        currentGridSpacing = parseFloat(data.spacing || 1.35);
        currentStopLossMode = data.stop_loss_mode || 'hold';
        if (document.getElementById('stratStopLossMode')) document.getElementById('stratStopLossMode').value = currentStopLossMode;
        if (document.getElementById('stratTrailingGrid') && data.trailing_grid !== undefined) document.getElementById('stratTrailingGrid').value = String(data.trailing_grid);
        if (cachedRawTrades && cachedRawTrades.length > 0) renderPairedOperations(cachedRawTrades);

        currentBotRunning = Boolean(data.is_running);
        updateBotStatusUI(currentBotRunning);
        highlightActivePreset(data.mode || 'equilibrado');
        updateGridLevelsExplainer();
    } catch (e) {
        console.warn('Aviso cargando estrategia del grid:', e);
    }
}

/**
 * Función: updateGridLevelsExplainer - Calcula y proyecta didácticamente el reparto de niveles de compra/venta y el importe por orden.
 */
function updateGridLevelsExplainer() {
    const levels = parseInt(document.getElementById('stratLevels')?.value || 8);
    const capital = parseFloat(document.getElementById('stratCapital')?.value || 16.0);
    const gridMin = parseFloat(document.getElementById('stratGridMin')?.value || 0), gridMax = parseFloat(document.getElementById('stratGridMax')?.value || 0);
    const livePrice = currentLivePrice || ((gridMin + gridMax) / 2) || 0.035;

    if (document.getElementById('expLevelsCount')) document.getElementById('expLevelsCount').textContent = levels;
    if (document.getElementById('expTotalSteps')) document.getElementById('expTotalSteps').textContent = levels;

    const perOrder = levels > 0 ? (capital / levels) : 0;
    if (document.getElementById('expPerOrderVal')) document.getElementById('expPerOrderVal').textContent = `~$${perOrder.toFixed(2)} USDT`;

    const badge = document.getElementById('expKucoinBadge');
    if (badge) {
        badge.className = 'badge-side ' + (perOrder >= 1.0 ? 'badge-buy' : 'badge-pending');
        badge.textContent = perOrder >= 1.0 ? '✅ Cumple Mínimo KuCoin' : '⚠️ Menor a $1 USDT (Subir capital)';
    }

    let buyCount = 0, sellCount = 0;
    if (gridMax > gridMin && levels > 1 && livePrice > 0) {
        const step = (gridMax - gridMin) / (levels - 1);
        for (let i = 0; i < levels; i++) {
            const p = gridMin + (i * step);
            if (p < livePrice * 0.998) buyCount++;
            else if (p > livePrice * 1.002) sellCount++;
        }
    } else {
        buyCount = Math.floor(levels / 2);
        sellCount = levels - buyCount;
    }

    if (document.getElementById('expBuyLevelsVal')) document.getElementById('expBuyLevelsVal').textContent = `~${buyCount} Compras`;
    if (document.getElementById('expSellLevelsVal')) document.getElementById('expSellLevelsVal').textContent = `~${sellCount} Ventas`;
}

/**
 * Función: updateBotStatusUI - Actualiza el badge y el botón de pausa/reanudación del bot.
 */
function updateBotStatusUI(isRunning) {
    const badge = document.getElementById('botStatusBadge');
    const btn = document.getElementById('btnToggleBot');
    if (badge) {
        badge.className = 'badge-side ' + (isRunning ? 'badge-buy' : 'badge-pending');
        badge.textContent = isRunning ? '🟢 BOT OPERANDO' : '⏸️ BOT PAUSADO';
    }
    if (btn) btn.textContent = isRunning ? '⏸️ Pausar Bot' : '▶️ Reanudar Bot';
}

/**
 * Función: highlightActivePreset - Marca el botón del preset seleccionado.
 */
function highlightActivePreset(modeName) {
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    const btnMap = { 'conservador': 'presetConservador', 'equilibrado': 'presetEquilibrado', 'scalping': 'presetScalping', 'personalizado': 'presetPersonalizado' };
    const targetBtn = document.getElementById(btnMap[modeName] || 'presetPersonalizado');
    if (targetBtn) targetBtn.classList.add('active');
}

/**
 * Función: applyPreset - Modifica los campos del formulario con los valores de la estrategia seleccionada incluyendo Stop-Loss.
 */
function applyPreset(preset) {
    highlightActivePreset(preset);
    const p = currentLivePrice || 0.0356, dec = (p < 1.0) ? 5 : ((p > 50) ? 2 : 4);
    let sp = 1.35, lv = 8, minRatio = 0.94, maxRatio = 1.08;
    if (preset === 'conservador') { sp = 1.80; lv = 6; minRatio = 0.92; maxRatio = 1.10; }
    else if (preset === 'scalping') { sp = 0.95; lv = 10; minRatio = 0.96; maxRatio = 1.05; }
    const minV = p * minRatio;
    document.getElementById('stratSpacing').value = sp;
    document.getElementById('stratLevels').value = lv;
    document.getElementById('stratGridMin').value = minV.toFixed(dec);
    document.getElementById('stratGridMax').value = (p * maxRatio).toFixed(dec);
    if (document.getElementById('stratStopLoss')) document.getElementById('stratStopLoss').value = (minV * 0.95).toFixed(dec);
    updateGridLevelsExplainer();
}

/**
 * Función: saveStrategyConfig - Envía la nueva configuración de la estrategia al backend para guardarla y rebalancear.
 */
async function saveStrategyConfig() {
    const btn = document.getElementById('btnSaveStrategy'), msg = document.getElementById('strategyStatusMsg');
    const symbol = document.getElementById('stratSymbol')?.value || 'KAS/USDT';
    const gridMin = parseFloat(document.getElementById('stratGridMin')?.value || 0), gridMax = parseFloat(document.getElementById('stratGridMax')?.value || 0);
    const spacing = parseFloat(document.getElementById('stratSpacing')?.value || 0), levels = parseInt(document.getElementById('stratLevels')?.value || 0);
    const capital = parseFloat(document.getElementById('stratCapital')?.value || 0), stopLoss = parseFloat(document.getElementById('stratStopLoss')?.value) || (gridMin * 0.95);
    const stopLossMode = document.getElementById('stratStopLossMode')?.value || 'hold', trailingGrid = document.getElementById('stratTrailingGrid')?.value === 'true';

    let mode = 'personalizado';
    const activeBtn = document.querySelector('.preset-btn.active');
    if (activeBtn?.id === 'presetConservador') mode = 'conservador';
    else if (activeBtn?.id === 'presetEquilibrado') mode = 'equilibrado';
    else if (activeBtn?.id === 'presetScalping') mode = 'scalping';

    if (!gridMin || !gridMax || !spacing || !levels || !capital) {
        if (msg) { msg.className = 'modal-status error'; msg.textContent = '⚠️ Todos los campos son obligatorios y deben ser numéricos.'; msg.style.display = 'block'; }
        return;
    }
    if (btn) { btn.disabled = true; btn.textContent = 'Aplicando en KuCoin...'; }

    try {
        const resp = await fetch('/api/grid/strategy', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol, grid_min: gridMin, grid_max: gridMax, spacing, num_levels: levels, capital, stop_loss_price: stopLoss, stop_loss_mode: stopLossMode, trailing_grid: trailingGrid, mode })
        });
        const res = await resp.json();
        if (btn) { btn.disabled = false; btn.textContent = '💾 Guardar y Aplicar a KuCoin'; }
        if (res.success) {
            if (msg) { msg.className = 'modal-status success'; msg.textContent = '✅ ' + res.message; msg.style.display = 'block'; }
            setTimeout(() => { if (msg) msg.style.display = 'none'; refreshDashboard(); }, 3000);
        } else if (msg) {
            msg.className = 'modal-status error'; msg.textContent = '❌ ' + (res.error || 'No se pudo aplicar la estrategia'); msg.style.display = 'block';
        }
    } catch (e) {
        if (btn) { btn.disabled = false; btn.textContent = '💾 Guardar y Aplicar a KuCoin'; }
        if (msg) { msg.className = 'modal-status error'; msg.textContent = '❌ Error de comunicación con el servidor.'; msg.style.display = 'block'; }
    }
}

/**
 * Función: rebalanceGrid - Solicita la reconstrucción inmediata de la cuadrícula en KuCoin.
 */
async function rebalanceGrid() {
    if (!confirm('¿Deseas cancelar las órdenes obsoletas y rebalancear la cuadrícula completa en KuCoin ahora?')) return;
    try {
        const resp = await fetch('/api/grid/rebalance', { method: 'POST' });
        const res = await resp.json();
        alert(res.message || 'Rebalanceo solicitado.');
        setTimeout(refreshDashboard, 2000);
    } catch (e) {
        alert('Error al solicitar rebalanceo: ' + e);
    }
}

/**
 * Función: syncOrphanSells - Revisa el saldo de KAS libre y coloca la orden de venta que faltase.
 */
async function syncOrphanSells() {
    try {
        const resp = await fetch('/api/grid/sync-orphans', { method: 'POST' });
        const res = await resp.json();
        alert(res.message || 'Reconciliación solicitada.');
        setTimeout(refreshDashboard, 2000);
    } catch (e) {
        alert('Error al sincronizar inventario: ' + e);
    }
}

/**
 * Función: toggleBotState - Alterna el estado del Grid Bot (Pausar / Reanudar).
 */
async function toggleBotState() {
    const action = currentBotRunning ? 'pausar' : 'reanudar';
    if (!confirm(`¿Confirmas que deseas ${action} el Grid Bot?`)) return;

    try {
        const resp = await fetch('/api/grid/toggle-state', { method: 'POST' });
        const res = await resp.json();
        if (res.success) {
            currentBotRunning = Boolean(res.is_running);
            updateBotStatusUI(currentBotRunning);
            alert(res.message || 'Estado actualizado.');
        }
    } catch (e) {
        alert('Error al alternar estado del bot: ' + e);
    }
}

/**
 * Función: refreshDashboard - Recarga manualmente todos los datos del dashboard.
 */
async function refreshDashboard() {
    const btn = document.getElementById('btnRefresh');
    if (btn) btn.textContent = '⏳ Cargando...';
    await Promise.all([
        fetchLivePrice(),
        loadActiveOrders(),
        loadMetrics(),
        loadStrategyConfig()
    ]);
    if (btn) btn.textContent = '🔄 Actualizar';
}

/**
 * Inicialización de eventos y ciclos de actualización del panel.
 */
document.addEventListener('DOMContentLoaded', () => {
    initTradingViewWidget(currentCoin);
    refreshDashboard();

    const coinSelect = document.getElementById('coinSelect');
    if (coinSelect) {
        coinSelect.addEventListener('change', (e) => {
            currentCoin = e.target.value;
            initTradingViewWidget(currentCoin);
            fetchLivePrice();
        });
    }

    [['btnOpenConfig', window.openConfigModal], ['btnCloseConfig', window.closeConfigModal], ['btnCancelConfig', window.closeConfigModal], ['btnSaveConfig', saveKucoinCredentials], ['btnOpenGridBot', window.openGridBotModal], ['btnCloseGridBot', window.closeGridBotModal], ['btnCancelGridBot', window.closeGridBotModal]].forEach(([id, fn]) => document.getElementById(id)?.addEventListener('click', fn));
    document.getElementById('configModal')?.addEventListener('click', (e) => { if (e.target.id === 'configModal') window.closeConfigModal(); });
    document.getElementById('gridBotModal')?.addEventListener('click', (e) => { if (e.target.id === 'gridBotModal') window.closeGridBotModal(); });
    ['stratLevels', 'stratCapital', 'stratGridMin', 'stratGridMax'].forEach(id => document.getElementById(id)?.addEventListener('input', updateGridLevelsExplainer));

    const slModeSel = document.getElementById('stratStopLossMode');
    if (slModeSel) {
        slModeSel.addEventListener('change', (e) => {
            currentStopLossMode = e.target.value;
            if (cachedRawTrades && cachedRawTrades.length > 0) {
                renderPairedOperations(cachedRawTrades);
            }
        });
    }

    loadRulesAndLearning();
    document.getElementById('aiLessonsCategoryFilter')?.addEventListener('change', () => loadRulesAndLearning());
    setInterval(fetchLivePrice, 5000);
    setInterval(loadActiveOrders, 15000);
    setInterval(loadMetrics, 30000);
    setInterval(loadStrategyConfig, 30000);
    setInterval(loadRulesAndLearning, 30000);
});

/**
 * Función: loadRulesAndLearning - Consulta las políticas activas del bot, las lecciones aprendidas por IA desde SQLite y las recomendaciones del día.
 */
async function loadRulesAndLearning() {
    try {
        const catFilter = document.getElementById('aiLessonsCategoryFilter')?.value || 'todas';
        const [respRules, respRec] = await Promise.all([
            fetch(`/api/learning/rules?category=${catFilter}`),
            fetch('/api/learning/daily-recommendation')
        ]);
        const data = await respRules.json();
        const recData = await respRec.json();
        if (!data) return;

        const grid = document.getElementById('aiRulesGrid');
        if (grid && data.rules) {
            grid.innerHTML = data.rules.map(r => `
                <div style="background:#161b22;border:1px solid #30363d;border-radius:6px;padding:10px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
                        <span style="font-size:12px;font-weight:600;color:#c9d1d9;">🛡️ ${r.title}</span>
                        <span class="badge-side ${r.badge}" style="font-size:9px;">${r.status}</span>
                    </div>
                    <p style="font-size:11px;color:#8b949e;margin:0 0 4px 0;">${r.desc}</p>
                    <div style="font-size:11px;font-weight:600;color:#58a6ff;">${r.metric}</div>
                </div>`).join('');
        }

        const lessons = document.getElementById('aiLessonsList');
        if (lessons && data.lessons) {
            lessons.innerHTML = data.lessons.map(l => `<div style="display:flex;align-items:center;gap:6px;padding:5px 8px;background:#161b22;border-radius:4px;border-left:3px solid #58a6ff;"><span>${l.icon}</span><span style="color:#c9d1d9;flex:1;">${l.text}</span><span style="font-size:10px;color:#8b949e;">(${l.time})</span></div>`).join('');
        }

        // Renderizar Recomendación del Día de la IA
        if (recData && recData.success && recData.recommendation) {
            const r = recData.recommendation;
            const dateEl = document.getElementById('aiRecDate');
            const ratEl = document.getElementById('aiRecRationale');
            const actList = document.getElementById('aiRecActionsList');
            const avList = document.getElementById('aiRecAvoidsList');
            if (dateEl) dateEl.textContent = r.report_date || 'Hoy';
            if (ratEl) ratEl.textContent = r.rationale || '';
            if (actList && r.actions) {
                actList.innerHTML = r.actions.map(a => `<li>${a}</li>`).join('');
            }
            if (avList && r.things_to_avoid) {
                avList.innerHTML = r.things_to_avoid.map(av => `<li>${av}</li>`).join('');
            }
        }

        // Actualización del Tacómetro de Miedo y Codicia de CoinMarketCap (CMC)
        if (data.fear_and_greed) {
            updateCmcFearAndGreedGauge(data.fear_and_greed);
        }

        // Consultar y sincronizar estado del botón Seguir Bot
        try {
            const respFollow = await fetch('/api/learning/follow-ai');
            const dataFollow = await respFollow.json();
            if (dataFollow && dataFollow.success) {
                updateFollowAiButtonUI(dataFollow.follow_ai);
            }
        } catch (fe) { console.warn('Aviso sincronizando follow-ai:', fe); }

        const timeEl = document.getElementById('aiLastUpdate');
        if (timeEl) timeEl.textContent = 'Actualizado: ' + new Date().toLocaleTimeString('es-ES');
    } catch (e) { console.warn('Aviso cargando reglas IA:', e); }
}

/**
 * Función: updateFollowAiButtonUI - Actualiza visualmente el botón Seguir Bot (colores, texto e indicador).
 */
function updateFollowAiButtonUI(isFollowing) {
    const btn = document.getElementById('btnToggleFollowAi');
    const dot = document.getElementById('followAiDot');
    const txt = document.getElementById('followAiText');
    if (!btn || !dot || !txt) return;

    if (isFollowing) {
        btn.style.background = 'rgba(46, 160, 67, 0.2)';
        btn.style.borderColor = '#2ea043';
        btn.style.color = '#3fb950';
        dot.style.background = '#3fb950';
        txt.textContent = 'Seguir Bot: ON';
    } else {
        btn.style.background = '#21262d';
        btn.style.borderColor = '#30363d';
        btn.style.color = '#8b949e';
        dot.style.background = '#8b949e';
        txt.textContent = 'Seguir Bot: OFF';
    }
}

/**
 * Función: toggleFollowAi - Activa o desactiva el modo de seguimiento automático de recomendaciones de la IA.
 */
async function toggleFollowAi() {
    const btn = document.getElementById('btnToggleFollowAi');
    const txt = document.getElementById('followAiText');
    const isCurrentlyOn = txt ? txt.textContent.includes('ON') : false;
    const action = isCurrentlyOn ? 'desactivar y volver a tu configuración manual' : 'activar y seguir las recomendaciones automáticas del bot';

    if (!confirm(`¿Confirmas que deseas ${action}?`)) return;

    if (btn) btn.disabled = true;
    try {
        const resp = await fetch('/api/learning/follow-ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: !isCurrentlyOn })
        });
        const res = await resp.json();
        if (res.success) {
            updateFollowAiButtonUI(res.follow_ai);
            alert(res.message || 'Configuración actualizada con éxito.');
            setTimeout(refreshDashboard, 1500);
        } else {
            alert('❌ Error: ' + (res.error || 'No se pudo cambiar el modo.'));
        }
    } catch (e) {
        alert('❌ Error de comunicación con el servidor: ' + e);
    } finally {
        if (btn) btn.disabled = false;
    }
}

/**
 * Función: updateCmcFearAndGreedGauge - Actualiza el indicador semicircular SVG, el valor numérico, la etiqueta en español y la aguja/dot.
 */
function updateCmcFearAndGreedGauge(fng) {
    const score = parseInt(fng.score !== undefined ? fng.score : 50, 10);
    const label = fng.label_es || fng.classification || 'Neutral';
    const numEl = document.getElementById('cmcScoreNum'), labelEl = document.getElementById('cmcScoreLabel');
    if (numEl) numEl.textContent = score;
    if (labelEl) {
        labelEl.textContent = label;
        labelEl.style.color = score >= 75 ? '#16c784' : (score >= 55 ? '#93c332' : (score >= 45 ? '#f5a623' : (score >= 25 ? '#f66e3b' : '#ea3943')));
    }
    const dot = document.getElementById('cmcGaugeDot');
    if (dot) {
        const clamped = Math.max(0, Math.min(100, score));
        const rad = ((180 - (clamped * 1.8)) * Math.PI) / 180;
        dot.setAttribute('cx', (100 + 75 * Math.cos(rad)).toFixed(1));
        dot.setAttribute('cy', (100 - 75 * Math.sin(rad)).toFixed(1));
    }
    const hist = fng.historical || {};
    const yestEl = document.getElementById('cmcHistYesterday'), weekEl = document.getElementById('cmcHistWeek');
    if (yestEl && hist.yesterday) yestEl.textContent = `${hist.yesterday.score} (${translateCmcName(hist.yesterday.name)})`;
    if (weekEl && hist.lastWeek) weekEl.textContent = `${hist.lastWeek.score} (${translateCmcName(hist.lastWeek.name)})`;
    const badgeEl = document.getElementById('cmcFngBadge');
    if (badgeEl && fng.source) badgeEl.textContent = `${fng.source} • Regulación 4x/día`;
}

/**
 * Función: translateCmcName - Traduce las categorías de sentimiento de CoinMarketCap a español.
 */
function translateCmcName(name) {
    if (!name) return '—';
    const map = {'Extreme fear': 'Miedo Extremo', 'Fear': 'Miedo', 'Neutral': 'Neutral', 'Greed': 'Codicia', 'Extreme greed': 'Codicia Extrema'};
    return map[name] || name;
}

/**
 * Función: triggerMarketSell - Cancela la orden límite en KuCoin y ejecuta la venta inmediata a precio de mercado.
 */
async function triggerMarketSell(amount, buyPrice) {
    const sym = document.getElementById('stratSymbol')?.value || 'KAS/USDT';
    const base = sym.split('/')[0];
    if (!confirm(`¿Confirmas que deseas cancelar la orden límite en KuCoin y VENDER AHORA a mercado ${amount} ${base}?`)) return;
    try {
        const resp = await fetch('/api/trades/market-sell', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ amount: amount, symbol: sym }) });
        const res = await resp.json();
        alert(res.success ? '✅ ' + res.message : '❌ Error: ' + (res.error || 'Rechazada'));
        if (res.success) setTimeout(refreshDashboard, 1500);
    } catch (e) { alert('❌ Error de comunicación: ' + e); }
}

/**
 * Función: triggerCancelOrder - Cancela una orden límite individual activa directamente en el exchange KuCoin.
 */
async function triggerCancelOrder(orderId, type, price, quantity) {
    const sym = document.getElementById('stratSymbol')?.value || 'KAS/USDT';
    if (!confirm(`¿Confirmas que deseas desactivar y QUITAR esta orden de ${type.toUpperCase()} (${quantity} a $${price}) de KuCoin?`)) return;
    try {
        const resp = await fetch('/api/orders/cancel', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ order_id: orderId, symbol: sym }) });
        const res = await resp.json();
        alert(res.success ? '✅ ' + res.message : '❌ Error: ' + (res.error || 'Rechazada'));
        if (res.success) refreshDashboard();
    } catch (e) { alert('❌ Error de comunicación: ' + e); }
}
