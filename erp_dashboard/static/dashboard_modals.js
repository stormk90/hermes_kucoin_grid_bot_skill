/**
 * ==============================================================================
 * GESTIÓN DEL MODAL DE SEGURIDAD PARA CREDENCIALES KUCOIN
 * ==============================================================================
 */
/**
 * Función: openConfigModal
 * Abre el diálogo modal de configuración de claves de API de KuCoin y consulta el estado actual.
 */
window.openConfigModal = function() {
    const modal = document.getElementById('configModal'), msg = document.getElementById('modalStatusMsg'), help = document.getElementById('currentKeyHelp');
    if (msg) msg.style.display = 'none';
    if (modal) modal.style.display = 'flex';
    if (help) help.textContent = 'Consultando clave actual en el servidor...';
    fetch('/api/config/keys').then(r => r.json()).then(data => {
        if (help) help.textContent = 'Clave actual: ' + (data.api_key_masked || 'No configurada');
    }).catch(() => { if (help) help.textContent = 'Clave actual: No disponible'; });
};

/**
 * Función: closeConfigModal
 * Cierra el diálogo modal de configuración de API de KuCoin.
 */
window.closeConfigModal = function() {
    const modal = document.getElementById('configModal');
    if (modal) modal.style.display = 'none';
};

/**
 * Función: openGridBotModal
 * Abre el modal de configuración de estrategias y controles operativos del Grid Bot.
 */
window.openGridBotModal = function() {
    const modal = document.getElementById('gridBotModal');
    const msg = document.getElementById('strategyStatusMsg');
    if (msg) msg.style.display = 'none';
    if (modal) modal.style.display = 'flex';
    loadStrategyConfig();
};

/**
 * Función: closeGridBotModal
 * Cierra el modal del Grid Bot.
 */
window.closeGridBotModal = function() {
    const modal = document.getElementById('gridBotModal');
    if (modal) modal.style.display = 'none';
};

/**
 * Función: saveKucoinCredentials
 * Envía las nuevas claves a /api/config/keys con cifrado seguro y reinicia el bot.
 */
async function saveKucoinCredentials() {
    const keyInput = document.getElementById('cfgApiKey'), secInput = document.getElementById('cfgApiSecret'), passInput = document.getElementById('cfgApiPassphrase');
    const msg = document.getElementById('modalStatusMsg'), btnSave = document.getElementById('btnSaveConfig');
    const apiKey = keyInput ? keyInput.value.trim() : '', apiSecret = secInput ? secInput.value.trim() : '', apiPassphrase = passInput ? passInput.value.trim() : '';

    if (!apiKey || !apiSecret || !apiPassphrase) {
        if (msg) { msg.className = 'modal-status error'; msg.textContent = '⚠️ Debes rellenar los 3 campos (Key, Secret y Passphrase).'; msg.style.display = 'block'; }
        return;
    }
    if (btnSave) { btnSave.disabled = true; btnSave.textContent = 'Guardando y Reiniciando...'; }

    try {
        const resp = await fetch('/api/config/keys', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret, api_passphrase: apiPassphrase })
        });
        const res = await resp.json();
        if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Guardar y Reiniciar Bot'; }
        if (res.success) {
            if (msg) { msg.className = 'modal-status success'; msg.textContent = '✅ Credenciales actualizadas y Grid Bot reiniciado con éxito.'; msg.style.display = 'block'; }
            setTimeout(() => {
                window.closeConfigModal();
                if (keyInput) keyInput.value = ''; if (secInput) secInput.value = ''; if (passInput) passInput.value = '';
                refreshDashboard();
            }, 1600);
        } else if (msg) {
            msg.className = 'modal-status error'; msg.textContent = '❌ Error: ' + (res.error || 'No se pudo guardar la configuración'); msg.style.display = 'block';
        }
    } catch (e) {
        if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Guardar y Reiniciar Bot'; }
        if (msg) { msg.className = 'modal-status error'; msg.textContent = '❌ Error de comunicación con el servidor.'; msg.style.display = 'block'; }
    }
}

/**
 * ==============================================================================
 * GESTIÓN DE LIQUIDACIÓN TOTAL DEL LOTE ACTUAL (VENTA A MERCADO CON CONFIRMACIÓN)
 * ==============================================================================
 */

// Variable global para almacenar los datos financieros del lote en memoria local
window.currentLoteInfo = null;

/**
 * Función: renderLotLiquidationCard
 * Descripción: Actualiza los valores de la tarjeta de liquidación en la sección 2 del panel
 *              (monedas KAS acumuladas, coste, valor de mercado, ganancia/pérdida del lote
 *              y el beneficio total neto proyectado para la cuenta del usuario).
 */
window.renderLotLiquidationCard = function(loteInfo) {
    if (!loteInfo) return;
    window.currentLoteInfo = loteInfo;

    const qtyBadge = document.getElementById('lotQtyBadge');
    const avgBuyPrice = document.getElementById('lotAvgBuyPrice');
    const marketVal = document.getElementById('lotMarketVal');
    const pnlDiff = document.getElementById('lotPnlDiff');
    const projTotal = document.getElementById('lotProjectedTotal');
    const btnOpen = document.getElementById('btnOpenLiquidateLot');

    const totalQty = parseFloat(loteInfo.total_qty || 0);

    if (totalQty <= 0) {
        if (qtyBadge) qtyBadge.textContent = '0 KAS (Sin compras pendientes)';
        if (avgBuyPrice) avgBuyPrice.textContent = '$0.00000';
        if (marketVal) marketVal.textContent = '$0.00 USDT';
        if (pnlDiff) {
            pnlDiff.textContent = '$0.00 (0.00%)';
            pnlDiff.style.color = '#8b949e';
        }
        if (projTotal) {
            const currPct = (loteInfo.curr_closed_pct >= 0 ? '+' : '') + Number(loteInfo.curr_closed_pct || 0).toFixed(2) + '%';
            projTotal.innerHTML = `<span style="color:#c9d1d9;">${currPct}</span> <span style="font-size:11px;color:#8b949e;">(Sin lote activo)</span>`;
        }
        if (btnOpen) {
            btnOpen.disabled = true;
            btnOpen.style.opacity = '0.5';
            btnOpen.style.cursor = 'not-allowed';
        }
        return;
    }

    if (qtyBadge) qtyBadge.textContent = `${totalQty.toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} KAS`;
    if (avgBuyPrice) avgBuyPrice.textContent = `$${Number(loteInfo.weighted_buy_price || 0).toFixed(5)}`;
    if (marketVal) marketVal.textContent = `$${Number(loteInfo.market_value || 0).toFixed(2)} USDT`;

    const netPnl = Number(loteInfo.net_pnl_usdt || 0);
    const pnlPct = Number(loteInfo.net_pnl_pct || 0);
    const sign = netPnl >= 0 ? '+' : '';
    const pctSign = pnlPct >= 0 ? '+' : '';
    const pnlColor = netPnl >= 0 ? '#3fb950' : '#f85149';

    if (pnlDiff) {
        pnlDiff.textContent = `${sign}$${netPnl.toFixed(2)} (${pctSign}${pnlPct.toFixed(2)}%)`;
        pnlDiff.style.color = pnlColor;
    }

    const currPct = (loteInfo.curr_closed_pct >= 0 ? '+' : '') + Number(loteInfo.curr_closed_pct || 0).toFixed(2) + '%';
    const projPct = (loteInfo.projected_total_pct >= 0 ? '+' : '') + Number(loteInfo.projected_total_pct || 0).toFixed(2) + '%';
    const projColor = Number(loteInfo.projected_total_pct || 0) >= 0 ? '#3fb950' : '#f85149';

    if (projTotal) {
        projTotal.innerHTML = `<span style="color:#c9d1d9;">${currPct}</span> → <span style="color:${projColor};font-weight:700;">${projPct}</span>`;
    }

    if (btnOpen) {
        btnOpen.disabled = false;
        btnOpen.style.opacity = '1';
        btnOpen.style.cursor = 'pointer';
    }
};

/**
 * Función: openLiquidateLotModal
 * Descripción: Despliega el modal de confirmación con el desglose detallado de números,
 *              impacto en beneficio total y el checkbox de confirmación explícita.
 */
window.openLiquidateLotModal = function() {
    const info = window.currentLoteInfo;
    if (!info || Number(info.total_qty || 0) <= 0) {
        alert('⚠️ En este momento no hay compras acumuladas pendientes de venta para liquidar.');
        return;
    }

    const modal = document.getElementById('liquidateLotModal');
    const chk = document.getElementById('chkConfirmLiquidate');
    const btn = document.getElementById('btnConfirmExecuteLiquidate');
    const msg = document.getElementById('liquidateLotStatusMsg');

    document.getElementById('modalLotQty').textContent = `${Number(info.total_qty).toLocaleString('es-ES', { minimumFractionDigits: 0, maximumFractionDigits: 2 })} KAS`;
    document.getElementById('modalLotCurPrice').textContent = `$${Number(info.current_price).toFixed(5)}`;
    document.getElementById('modalLotAvgBuy').textContent = `$${Number(info.weighted_buy_price).toFixed(5)}`;
    document.getElementById('modalLotCost').textContent = `$${Number(info.total_cost).toFixed(2)} USDT`;
    document.getElementById('modalLotVal').textContent = `$${Number(info.market_value).toFixed(2)} USDT`;

    const netPnl = Number(info.net_pnl_usdt || 0);
    const pnlPct = Number(info.net_pnl_pct || 0);
    const pnlColor = netPnl >= 0 ? '#3fb950' : '#f85149';
    const pnlEl = document.getElementById('modalLotPnl');
    pnlEl.textContent = `${netPnl >= 0 ? '+' : ''}$${netPnl.toFixed(2)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%)`;
    pnlEl.style.color = pnlColor;

    const currPct = (info.curr_closed_pct >= 0 ? '+' : '') + Number(info.curr_closed_pct || 0).toFixed(2) + '%';
    const projPct = (info.projected_total_pct >= 0 ? '+' : '') + Number(info.projected_total_pct || 0).toFixed(2) + '%';
    const projColor = Number(info.projected_total_pct || 0) >= 0 ? '#3fb950' : '#f85149';
    document.getElementById('modalLotProjected').innerHTML = `<span style="color:#c9d1d9;">${currPct}</span> → <span style="color:${projColor};font-weight:700;">${projPct}</span>`;

    const currClosedPnl = Number(info.curr_closed_pnl || 0);
    const projPnl = Number(info.projected_total_pnl || 0);
    document.getElementById('modalLotProjectedSub').textContent = `Beneficio cerrado actual: $${currClosedPnl.toFixed(2)} USDT | Proyectado tras venta: $${projPnl.toFixed(2)} USDT`;

    if (chk) chk.checked = false;
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
        btn.textContent = '⚡ Confirmar Liquidación';
    }
    if (msg) {
        msg.style.display = 'none';
        msg.textContent = '';
    }

    if (modal) modal.style.display = 'flex';
};

/**
 * Función: closeLiquidateLotModal
 * Descripción: Cierra el diálogo modal de confirmación de liquidación de lote.
 */
window.closeLiquidateLotModal = function() {
    const modal = document.getElementById('liquidateLotModal');
    if (modal) modal.style.display = 'none';
};

/**
 * Función: toggleConfirmLiquidateBtn
 * Descripción: Habilita o deshabilita el botón de venta a mercado según el estado del checkbox.
 */
window.toggleConfirmLiquidateBtn = function() {
    const chk = document.getElementById('chkConfirmLiquidate');
    const btn = document.getElementById('btnConfirmExecuteLiquidate');
    if (chk && btn) {
        btn.disabled = !chk.checked;
        btn.style.opacity = chk.checked ? '1' : '0.5';
        btn.style.cursor = chk.checked ? 'pointer' : 'not-allowed';
    }
};

/**
 * Función: executeLiquidateLot
 * Descripción: Envía la petición POST a /api/trades/liquidate-lot para cancelar órdenes límite
 *              en KuCoin y vender todo el inventario acumulado a precio de mercado.
 */
window.executeLiquidateLot = async function() {
    const btn = document.getElementById('btnConfirmExecuteLiquidate');
    const msg = document.getElementById('liquidateLotStatusMsg');

    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Cancelando órdenes y vendiendo en KuCoin...';
    }
    if (msg) {
        msg.className = 'modal-status';
        msg.style.display = 'block';
        msg.style.color = '#58a6ff';
        msg.textContent = '🔄 Ejecutando cancelación en KuCoin y venta a mercado...';
    }

    try {
        const resp = await fetch('/api/trades/liquidate-lot', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: 'KAS/USDT' })
        });
        const res = await resp.json();

        if (res.success) {
            if (msg) {
                msg.className = 'modal-status success';
                msg.style.color = '#3fb950';
                msg.textContent = '✅ ' + (res.message || 'Liquidación completada con éxito.');
            }
            if (btn) btn.textContent = '✅ Liquidación Realizada';
            setTimeout(() => {
                window.closeLiquidateLotModal();
                if (typeof refreshDashboard === 'function') refreshDashboard();
            }, 2000);
        } else {
            if (btn) {
                btn.disabled = false;
                btn.textContent = '⚡ Confirmar Liquidación';
            }
            if (msg) {
                msg.className = 'modal-status error';
                msg.style.color = '#f85149';
                msg.textContent = '❌ Error: ' + (res.error || 'No se pudo liquidar el lote.');
            }
        }
    } catch (e) {
        if (btn) {
            btn.disabled = false;
            btn.textContent = '⚡ Confirmar Liquidación';
        }
        if (msg) {
            msg.className = 'modal-status error';
            msg.style.color = '#f85149';
            msg.textContent = '❌ Error de comunicación con el servidor: ' + e;
        }
    }
};

/**
 * ==============================================================================
 * EJECUCIÓN MANUAL DE ANÁLISIS INTEGRAL DE MERCADO Y SENTIMIENTO
 * ==============================================================================
 */

/**
 * Función: triggerManualMarketAnalysis
 * Descripción: Invoca la ejecución inmediata del análisis técnico de KuCoin (RSI, ATR,
 *              niveles óptimos) y análisis de sentimiento (Fear & Greed, titulares RSS,
 *              recomendaciones SQLite), actualizando dinámicamente el panel y feedback visual.
 */
window.triggerManualMarketAnalysis = async function() {
    const btn = document.getElementById('btnRunMarketAnalysis');
    const originalText = btn ? btn.innerHTML : '';

    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.7';
        btn.style.cursor = 'wait';
        btn.innerHTML = '<span>⏳ Analizando Mercado...</span>';
    }

    try {
        const resp = await fetch('/api/learning/analyze-now', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const res = await resp.json();

        if (res.success) {
            if (btn) {
                btn.innerHTML = '<span>✅ ¡Análisis Completado!</span>';
                btn.style.background = '#1f6feb';
                btn.style.borderColor = '#388bfd';
            }

            // Refrescar reglas, recomendaciones y el panel completo
            if (typeof loadRulesAndLearning === 'function') loadRulesAndLearning();
            if (typeof refreshDashboard === 'function') refreshDashboard();

            setTimeout(() => {
                if (btn) {
                    btn.disabled = false;
                    btn.style.opacity = '1';
                    btn.style.cursor = 'pointer';
                    btn.style.background = '#238636';
                    btn.style.borderColor = '#2ea043';
                    btn.innerHTML = originalText || '<span>⚡ Analizar Mercado Ahora</span>';
                }
            }, 3000);
        } else {
            alert('❌ Error al analizar el mercado: ' + (res.error || 'Operación fallida'));
            if (btn) {
                btn.disabled = false;
                btn.style.opacity = '1';
                btn.style.cursor = 'pointer';
                btn.innerHTML = originalText || '<span>⚡ Analizar Mercado Ahora</span>';
            }
        }
    } catch (e) {
        alert('❌ Error de comunicación con el servidor: ' + e);
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.style.cursor = 'pointer';
            btn.innerHTML = originalText || '<span>⚡ Analizar Mercado Ahora</span>';
        }
    }
};

