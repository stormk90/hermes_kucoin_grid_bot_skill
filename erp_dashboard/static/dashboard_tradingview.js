// ==========================================================================
// MÓDULO OFICIAL DE GRÁFICOS KUCOIN CON ÓRDENES VIVAS (LIGHTWEIGHT CHARTS)
// Renderiza velas nativas OHLCV de KuCoin y dibuja las líneas de órdenes del bot.
// ==========================================================================

// Mapeo de pares a identificadores de monedas
const SYMBOL_TO_COIN = {
    'KAS/USDT': 'kaspa', 'BTC/USDT': 'bitcoin', 'ETH/USDT': 'ethereum', 'SOL/USDT': 'solana',
    'XRP/USDT': 'ripple', 'ADA/USDT': 'cardano', 'DOGE/USDT': 'dogecoin', 'DOT/USDT': 'polkadot',
    'LTC/USDT': 'litecoin', 'LINK/USDT': 'chainlink'
};

// Símbolos estándar de KuCoin
const KUCOIN_SYMBOLS = {
    'kaspa': 'KAS-USDT', 'bitcoin': 'BTC-USDT', 'ethereum': 'ETH-USDT', 'solana': 'SOL-USDT',
    'ripple': 'XRP-USDT', 'cardano': 'ADA-USDT', 'dogecoin': 'DOGE-USDT', 'polkadot': 'DOT-USDT',
    'litecoin': 'LTC-USDT', 'chainlink': 'LINK-USDT'
};

// Variables globales del gráfico
var currentCoin = window.currentCoin || 'kaspa';
var currentInterval = '15m';
var lwChartInstance = null;
var candleSeriesInstance = null;
var volumeSeriesInstance = null;
var chartOrderPriceLines = [];
var chartResizeObserver = null;
var latestCandleData = null;

/**
 * Función: formatCurrency
 * Formatea valores numéricos con decimales apropiados según la magnitud del precio.
 */
function formatCurrency(val, minDecimals = 4) {
    if (val === undefined || val === null || isNaN(val)) return '—';
    const num = parseFloat(val);
    if (num >= 100) return '$' + num.toFixed(2);
    if (num >= 1) return '$' + num.toFixed(4);
    return '$' + num.toFixed(minDecimals);
}

/**
 * Función: updateOhlcLegend
 * Actualiza la barra informativa superior con los valores OHLCV de la vela bajo el cursor.
 */
function updateOhlcLegend(candle, vol) {
    if (!candle) return;
    const isKas = (currentCoin === 'kaspa' || currentCoin === 'dogecoin' || currentCoin === 'cardano');
    const decimals = isKas ? 5 : 2;
    const isUp = (candle.close >= candle.open);
    const colorClass = isUp ? '#00c076' : '#ff5353';
    const chgPct = candle.open > 0 ? (((candle.close - candle.open) / candle.open) * 100) : 0;
    const sign = chgPct >= 0 ? '+' : '';

    const elOpen = document.getElementById('ohlc_open');
    const elHigh = document.getElementById('ohlc_high');
    const elLow = document.getElementById('ohlc_low');
    const elClose = document.getElementById('ohlc_close');
    const elVol = document.getElementById('ohlc_vol');
    const elChange = document.getElementById('ohlc_change');

    if (elOpen) elOpen.textContent = candle.open.toFixed(decimals);
    if (elHigh) elHigh.textContent = candle.high.toFixed(decimals);
    if (elLow) elLow.textContent = candle.low.toFixed(decimals);
    if (elClose) {
        elClose.textContent = candle.close.toFixed(decimals);
        elClose.style.color = colorClass;
    }
    if (elVol && vol !== undefined && vol !== null) {
        const v = typeof vol === 'object' ? (vol.value || 0) : vol;
        elVol.textContent = (v >= 1000000) ? (v / 1000000).toFixed(2) + 'M' : (v >= 1000 ? (v / 1000).toFixed(1) + 'K' : v.toFixed(0));
    }
    if (elChange) {
        elChange.textContent = sign + chgPct.toFixed(2) + '%';
        elChange.style.color = colorClass;
    }
}

/**
 * Función: onStrategySymbolChange
 * Sincroniza el par seleccionado en el panel con el gráfico KuCoin y recalcula límites sugeridos.
 */
async function onStrategySymbolChange() {
    const sel = document.getElementById('stratSymbol');
    if (!sel) return;
    const sym = sel.value;
    const coinId = SYMBOL_TO_COIN[sym] || 'kaspa';

    currentCoin = coinId;
    const coinSelect = document.getElementById('coinSelect');
    if (coinSelect) coinSelect.value = coinId;

    initTradingViewWidget(coinId);
    if (typeof fetchLivePrice === 'function') {
        await fetchLivePrice();
    }

    const p = (typeof currentLivePrice !== 'undefined' && currentLivePrice) ? currentLivePrice : 1.0;
    const decimals = (p < 1.0) ? 5 : ((p > 50) ? 2 : 4);
    
    const minInput = document.getElementById('stratGridMin');
    const maxInput = document.getElementById('stratGridMax');
    if (minInput) minInput.value = (p * 0.93).toFixed(decimals);
    if (maxInput) maxInput.value = (p * 1.07).toFixed(decimals);
}

/**
 * Función: initTradingViewWidget
 * Inicializa el gráfico nativo de KuCoin con Lightweight Charts.
 * Configura tema oscuro, escalas de precios/volumen y carga velas y órdenes vivas.
 */
function initTradingViewWidget(coinId) {
    if (coinId) currentCoin = coinId;
    const container = document.getElementById('tradingview_widget_box');
    if (!container) return;

    // Destruir instancia previa de forma segura
    if (chartResizeObserver) {
        chartResizeObserver.disconnect();
        chartResizeObserver = null;
    }
    if (lwChartInstance) {
        try { lwChartInstance.remove(); } catch (e) { console.warn('Aviso al destruir gráfico:', e); }
        lwChartInstance = null;
        candleSeriesInstance = null;
        volumeSeriesInstance = null;
        chartOrderPriceLines = [];
    }
    container.innerHTML = '';

    // Crear widget informativo superior de datos OHLCV al pasar cursor
    const legend = document.createElement('div');
    legend.id = 'chart_ohlc_legend';
    legend.className = 'chart-ohlc-legend';
    legend.innerHTML = `
        <span>O <b id="ohlc_open">—</b></span>
        <span>H <b id="ohlc_high">—</b></span>
        <span>L <b id="ohlc_low">—</b></span>
        <span>C <b id="ohlc_close">—</b></span>
        <span>Vol <b id="ohlc_vol">—</b></span>
        <span>Var <b id="ohlc_change">—</b></span>
    `;
    container.appendChild(legend);

    // Dimensiones iniciales del contenedor
    const width = container.clientWidth || 800;
    const height = 520;

    // Crear instancia de Lightweight Charts con estilo KuCoin Dark y fuente compacta
    try {
        lwChartInstance = LightweightCharts.createChart(container, {
            width: width,
            height: height,
            layout: {
                background: { type: 'solid', color: '#131722' },
                textColor: '#9598a1',
                fontSize: 11,
                fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
            },
            grid: {
                vertLines: { color: '#1f2431' },
                horzLines: { color: '#1f2431' }
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
                vertLine: { color: '#758696', width: 1, style: LightweightCharts.LineStyle.Dashed },
                horzLine: { color: '#758696', width: 1, style: LightweightCharts.LineStyle.Dashed }
            },
            rightPriceScale: {
                borderColor: '#2b2f3a',
                scaleMargins: { top: 0.08, bottom: 0.18 },
                autoScale: true
            },
            localization: {
                locale: 'es-ES',
                dateFormat: 'yyyy-MM-dd'
            },
            timeScale: {
                borderColor: '#2b2f3a',
                timeVisible: true,
                secondsVisible: false,
                barSpacing: 9,
                minBarSpacing: 1,
                rightOffset: 12
            },
            handleScale: {
                mouseWheel: true,
                pinch: true,
                axisPressedMouseMove: true
            },
            handleScroll: {
                mouseWheel: true,
                pressedMouseMove: true,
                horzTouchDrag: true,
                vertTouchDrag: true
            }
        });

        // Serie de Velas Japonesas (Estilo KuCoin: Verde #00c076, Rojo #ff5353)
        const isLowValueCoin = (currentCoin === 'kaspa' || currentCoin === 'dogecoin' || currentCoin === 'cardano');
        const precision = isLowValueCoin ? 5 : 2;
        const minMove = isLowValueCoin ? 0.00001 : 0.01;

        candleSeriesInstance = lwChartInstance.addCandlestickSeries({
            upColor: '#00c076',
            downColor: '#ff5353',
            borderVisible: false,
            wickUpColor: '#00c076',
            wickDownColor: '#ff5353',
            priceFormat: {
                type: 'price',
                precision: precision,
                minMove: minMove
            },
            autoscaleInfoProvider: (original) => {
                try {
                    const res = original();
                    if (!res || !res.priceRange) return res;
                    let min = res.priceRange.minValue;
                    let max = res.priceRange.maxValue;
                    const orders = (typeof window !== 'undefined' && window.cachedOpenOrders) ? window.cachedOpenOrders : [];
                    if (Array.isArray(orders) && orders.length > 0) {
                        orders.forEach(o => {
                            if (o.status !== 'cancelada' && o.price) {
                                const p = parseFloat(o.price);
                                if (p > 0 && Math.abs((p - min) / min) < 0.35) {
                                    if (p < min) min = p;
                                    if (p > max) max = p;
                                }
                            }
                        });
                    }
                    return {
                        priceRange: {
                            minValue: min,
                            maxValue: max
                        },
                        margins: res.margins
                    };
                } catch (e) {
                    return original();
                }
            }
        });

        // Serie de Histograma de Volumen (ajustada en la base inferior al 10% sin invadir velas)
        volumeSeriesInstance = lwChartInstance.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume_scale'
        });

        lwChartInstance.priceScale('volume_scale').applyOptions({
            scaleMargins: { top: 0.90, bottom: 0 }
        });

        // Suscripción al movimiento del cursor para mostrar datos OHLCV en vivo
        lwChartInstance.subscribeCrosshairMove(param => {
            if (!param || !param.time || !param.seriesData) {
                if (latestCandleData) {
                    updateOhlcLegend(latestCandleData.candle, latestCandleData.vol);
                }
                return;
            }
            const candle = param.seriesData.get(candleSeriesInstance);
            const vol = param.seriesData.get(volumeSeriesInstance);
            if (candle) {
                updateOhlcLegend(candle, vol);
            }
        });

        // Observador para redimensionar automáticamente el gráfico si cambia la ventana
        chartResizeObserver = new ResizeObserver(entries => {
            if (!entries || entries.length === 0 || !entries[0].contentRect) return;
            const newRect = entries[0].contentRect;
            if (lwChartInstance && newRect.width > 0) {
                lwChartInstance.applyOptions({ width: newRect.width, height: 520 });
            }
        });
        chartResizeObserver.observe(container);

        // Cargar velas de KuCoin
        loadKucoinCandles();

    } catch (err) {
        console.error('Error al inicializar gráfico KuCoin Lightweight Charts:', err);
    }
}

/**
 * Función: loadKucoinCandles
 * Consulta el endpoint oficial de velas del backend para el par y temporalidad seleccionados.
 */
async function loadKucoinCandles(isBackgroundRefresh = false) {
    if (!candleSeriesInstance || !volumeSeriesInstance) return;
    try {
        const symbol = KUCOIN_SYMBOLS[currentCoin] || 'KAS-USDT';
        const resp = await fetch(`/api/chart/candles?coin=${currentCoin}&symbol=${symbol}&interval=${currentInterval}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        if (data.success && data.candles && data.candles.length > 0) {
            // Conversión de marcas de tiempo UTC a la zona horaria local del navegador
            // Lightweight Charts renderiza marcas de tiempo numéricas en UTC internamente,
            // por lo que se ajusta el offset local para que las etiquetas del eje muestren la hora local del usuario.
            const tzOffsetSec = -new Date().getTimezoneOffset() * 60;
            const localCandles = data.candles.map(c => ({
                ...c,
                time: c.time + tzOffsetSec
            }));
            const localVolumes = (data.volumes || []).map(v => ({
                ...v,
                time: v.time + tzOffsetSec
            }));

            candleSeriesInstance.setData(localCandles);
            volumeSeriesInstance.setData(localVolumes);

            // Guardar última vela y actualizar barra de datos OHLCV
            const lastCandle = localCandles[localCandles.length - 1];
            const lastVol = (localVolumes && localVolumes.length > 0) ? localVolumes[localVolumes.length - 1] : null;
            latestCandleData = { candle: lastCandle, vol: lastVol };
            updateOhlcLegend(lastCandle, lastVol);
            const lastUpEl = document.getElementById('chartLastUpdatedTime');
            if (lastUpEl) lastUpEl.textContent = new Date().toLocaleTimeString();

            // Ajustar vista inicial solo si no es un refresco en segundo plano,
            // respetando el zoom y la posición actual que el usuario esté examinando
            if (!isBackgroundRefresh && lwChartInstance) {
                const totalBars = data.candles.length;
                lwChartInstance.timeScale().setVisibleLogicalRange({
                    from: Math.max(0, totalBars - 75),
                    to: totalBars + 6
                });
            }

            // Actualizar título del gráfico
            const titleEl = document.getElementById('chartSymbolTitle');
            if (titleEl) {
                const coinName = currentCoin.toUpperCase() + '/USDT';
                titleEl.textContent = `${coinName} · ${currentInterval} · KuCoin`;
            }

            // Dibujar líneas de órdenes con el precio actual de la vela en caché
            if (typeof cachedOpenOrders !== 'undefined' && cachedOpenOrders.length > 0) {
                drawChartOrderLines(cachedOpenOrders, lastCandle.close);
            }
        }
    } catch (err) {
        console.warn('Aviso al cargar velas KuCoin:', err);
    }
}

/**
 * Función: changeChartInterval
 * Cambia la temporalidad de las velas KuCoin (1m, 5m, 15m, 1h, 4h, 1D) y recarga el gráfico.
 */
function changeChartInterval(interval) {
    currentInterval = interval;

    // Actualizar botones en la interfaz
    const btns = document.querySelectorAll('.interval-btn');
    btns.forEach(btn => {
        if (btn.getAttribute('data-interval') === interval) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    loadKucoinCandles();
}

/**
 * Función: drawChartOrderLines
 * Dibuja las líneas discontinuas horizontales de órdenes activas (verdes para compras, rojas para ventas),
 * mostrando limpiamente solo el precio en el eje vertical sin banners de texto invasivos que ensucien las velas.
 */
function drawChartOrderLines(orders, activePrice) {
    try {
        if (!candleSeriesInstance) return;

        // Eliminar líneas de órdenes previas
        if (chartOrderPriceLines.length > 0) {
            chartOrderPriceLines.forEach(line => {
                try { candleSeriesInstance.removePriceLine(line); } catch (e) {}
            });
            chartOrderPriceLines = [];
        }

        if (!orders || !Array.isArray(orders) || orders.length === 0) return;

        // Guardar órdenes en variable global para el proveedor de autoescala
        window.cachedOpenOrders = orders;

        // Obtener precio de referencia vigente garantizado para calcular la distancia exacta
        const cPrice = (activePrice && activePrice > 0)
            ? activePrice
            : ((latestCandleData && latestCandleData.candle && latestCandleData.candle.close > 0)
                ? latestCandleData.candle.close
                : ((typeof window.currentLivePrice !== 'undefined' && window.currentLivePrice > 0)
                    ? window.currentLivePrice
                    : ((typeof currentLivePrice !== 'undefined' && currentLivePrice > 0)
                        ? currentLivePrice
                        : 0)));

        orders.forEach(ord => {
            if (ord.status === 'cancelada' || !ord.price) return;

            const isBuy = (ord.type === 'compra' || ord.side === 'buy');
            const lineColor = isBuy ? '#00c076' : '#ff5353';
            const priceNum = parseFloat(ord.price);

            // Distancia porcentual exacta que queda desde el precio actual hasta la ejecución de la orden
            let pctText = '';
            if (cPrice > 0 && priceNum > 0) {
                const diffPct = ((priceNum - cPrice) / cPrice) * 100;
                const sign = diffPct > 0 ? '+' : '';
                pctText = `${sign}${diffPct.toFixed(2)}%`;
            }

            try {
                // Línea con etiqueta de precio en el eje y distintivo con la distancia a la ejecución
                const priceLine = candleSeriesInstance.createPriceLine({
                    price: priceNum,
                    color: lineColor,
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: pctText,
                    axisLabelColor: lineColor,
                    axisLabelTextColor: '#ffffff',
                    titleColor: '#2563eb', // Azul eléctrico distintivo para el porcentaje
                    titleTextColor: '#ffffff'
                });
                chartOrderPriceLines.push(priceLine);
            } catch (err) {
                console.warn('Aviso al trazar línea de orden en gráfico:', err);
            }
        });

        // Forzar recálculo dinámico del rango vertical para incluir todas las órdenes
        try {
            candleSeriesInstance.applyOptions({});
        } catch (e) {}

    } catch (globalErr) {
        console.error('Error en drawChartOrderLines:', globalErr);
    }
}

// Exportar funciones globalmente para sincronización con dashboard.js
window.initTradingViewWidget = initTradingViewWidget;
window.changeChartInterval = changeChartInterval;
window.updateChartOrderLines = drawChartOrderLines;
window.drawChartOrderLines = drawChartOrderLines;
window.loadKucoinCandles = loadKucoinCandles;

// Ciclo de actualización automática de velas de KuCoin cada 10 segundos en segundo plano
setInterval(() => {
    if (typeof loadKucoinCandles === 'function' && document.visibilityState === 'visible') {
        loadKucoinCandles(true);
    }
}, 10000);
